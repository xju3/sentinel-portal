"""Reliable Redis Stream consumer for uploaded FFT objects."""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

import redis as redis_lib

from app.config import settings
from pub.services.sensor.sensor_task_service import process_fft_metadata_background
from pub.utils.redis_keys import REDIS_STREAM_FFT_GROUP, REDIS_STREAM_FFT_TRIGGER

logger = logging.getLogger(__name__)

BLOCK_MS = 2000
PENDING_MIN_IDLE_MS = 60_000
PENDING_SCAN_INTERVAL_SECONDS = 30


def _create_worker_redis() -> redis_lib.Redis:
    return redis_lib.from_url(
        settings.stream_redis_url,
        decode_responses=True,
        socket_timeout=(BLOCK_MS / 1000) + 3.0,
        socket_connect_timeout=3.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )


def ensure_fft_consumer_group() -> None:
    client = _create_worker_redis()
    try:
        client.xgroup_create(
            REDIS_STREAM_FFT_TRIGGER,
            REDIS_STREAM_FFT_GROUP,
            id="0",
            mkstream=True,
        )
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    finally:
        client.close()


async def _process_message(
    *,
    client,
    worker_id: str,
    message_id: str,
    fields: dict,
) -> None:
    try:
        task_id = UUID(str(fields.get("task_id", "")))
    except (TypeError, ValueError):
        logger.error(
            "Invalid FFT trigger: message_id=%s fields=%s",
            message_id,
            fields,
        )
        await asyncio.to_thread(
            client.xack,
            REDIS_STREAM_FFT_TRIGGER,
            REDIS_STREAM_FFT_GROUP,
            message_id,
        )
        return

    try:
        completed = await process_fft_metadata_background(task_id)
    except Exception:
        logger.exception(
            "FFT diagnosis failed; message remains pending: task_id=%s",
            task_id,
        )
        return
    if not completed:
        logger.error(
            "FFT diagnosis incomplete; message remains pending: task_id=%s",
            task_id,
        )
        return

    await asyncio.to_thread(
        client.xack,
        REDIS_STREAM_FFT_TRIGGER,
        REDIS_STREAM_FFT_GROUP,
        message_id,
    )
    logger.info(
        "FFT diagnosis acknowledged: worker=%s task_id=%s",
        worker_id,
        task_id,
    )


async def run_fft_stream_worker(worker_id: str) -> None:
    client = _create_worker_redis()
    last_pending_scan = 0.0
    while True:
        try:
            results = []
            now = time.monotonic()
            if now - last_pending_scan >= PENDING_SCAN_INTERVAL_SECONDS:
                claimed = await asyncio.to_thread(
                    client.xautoclaim,
                    REDIS_STREAM_FFT_TRIGGER,
                    REDIS_STREAM_FFT_GROUP,
                    worker_id,
                    PENDING_MIN_IDLE_MS,
                    "0-0",
                    count=1,
                )
                messages = claimed[1] if claimed and len(claimed) > 1 else []
                results = (
                    [(REDIS_STREAM_FFT_TRIGGER, messages)]
                    if messages
                    else []
                )
                last_pending_scan = now

            if not results:
                results = await asyncio.to_thread(
                    client.xreadgroup,
                    REDIS_STREAM_FFT_GROUP,
                    worker_id,
                    {REDIS_STREAM_FFT_TRIGGER: ">"},
                    count=1,
                    block=BLOCK_MS,
                )
            for _stream, messages in results or []:
                for message_id, fields in messages:
                    await _process_message(
                        client=client,
                        worker_id=worker_id,
                        message_id=message_id,
                        fields=fields,
                    )
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("FFT stream worker failed")
            await asyncio.sleep(5)
