import asyncio
import json
import logging
import time

import redis as redis_lib
from pub.manager.database import redis_manager
from pub.utils.redis_keys import REDIS_STREAM_DIAGNOSIS_TRIGGER, REDIS_STREAM_DIAGNOSIS_GROUP
from pub.models.report import DiagnosisTriggerPayload
from app.preparation.ingestion import process_incoming_report
from app.config import settings

logger = logging.getLogger(__name__)

# 每次从 Stream 拉取的最大消息数
WORKER_BATCH_SIZE = 5
# xreadgroup 阻塞等待时间（毫秒），避免空轮询 CPU 空转
BLOCK_MS = 2000
# 全局最大并发诊断数（所有 worker 共享），防止数据库连接被打爆
# 实际并发上限 = min(WORKER_COUNT * WORKER_BATCH_SIZE, MAX_CONCURRENT_DIAGNOSES)
MAX_CONCURRENT_DIAGNOSES = 10
PENDING_MIN_IDLE_MS = 60_000
PENDING_SCAN_INTERVAL_SECONDS = 30

# 全局信号量，在模块加载时创建
_diagnosis_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DIAGNOSES)


def _create_worker_redis() -> redis_lib.Redis:
    """为 stream worker 创建独立 Redis 连接。

    xreadgroup 的 block 参数会长期占用 socket，必须与全局业务连接（redis_manager）隔离。
    socket_timeout 设置为 BLOCK_MS + 3000ms，确保不会因超时误断阻塞等待。
    """
    socket_timeout = (BLOCK_MS / 1000) + 3.0
    return redis_lib.from_url(
        settings.stream_redis_url,
        decode_responses=True,
        socket_timeout=socket_timeout,
        socket_connect_timeout=3.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )


def _ensure_consumer_group() -> None:
    """
    确保 Stream 和 Consumer Group 存在。
    若 Stream 不存在，mkstream=True 会自动创建。
    若 Group 已存在，捕获 BUSYGROUP 异常忽略即可。
    """
    client = redis_manager.get_client()
    try:
        client.xgroup_create(
            REDIS_STREAM_DIAGNOSIS_TRIGGER,
            REDIS_STREAM_DIAGNOSIS_GROUP,
            id="0",          # 从最旧的消息开始消费（保证重启不丢）
            mkstream=True,
        )
        logger.debug("Created consumer group '%s' on stream '%s'.", REDIS_STREAM_DIAGNOSIS_GROUP, REDIS_STREAM_DIAGNOSIS_TRIGGER)
    except Exception as e:
        # BUSYGROUP Consumer Group name already exists
        if "BUSYGROUP" in str(e):
            logger.debug("Consumer group '%s' already exists, skipping creation.", REDIS_STREAM_DIAGNOSIS_GROUP)
        else:
            raise


async def _process_one_message(payload: DiagnosisTriggerPayload) -> None:
    """直接使用传递过来的轻量级 Payload 触发诊断流程"""
    await process_incoming_report(payload)


async def _handle_single_message(worker_id: str, client, msg_id: str, fields: dict) -> None:
    """
    处理单条 Stream 消息的完整生命周期：校验 → 获取信号量 → 处理 → ACK。
    """
    try:
        # fields might contain bytes if fetched directly from aioredis, decode them
        decoded_fields = {}
        for k, v in fields.items():
            key_str = k.decode('utf-8') if isinstance(k, bytes) else k
            val_str = v.decode('utf-8') if isinstance(v, bytes) else v
            # Only include non-empty values or values that should be mapped to None
            if val_str == "":
                decoded_fields[key_str] = None
            else:
                decoded_fields[key_str] = val_str
                
        payload = DiagnosisTriggerPayload.model_validate(decoded_fields)
    except Exception as e:
        logger.error("Worker '%s': malformed stream message id=%s: %s - %s", worker_id, msg_id, fields, e)
        # 格式错误，直接 ACK 丢弃，避免永久阻塞
        await asyncio.to_thread(client.xack, REDIS_STREAM_DIAGNOSIS_TRIGGER, REDIS_STREAM_DIAGNOSIS_GROUP, msg_id)
        return

    # 获取信号量：限制全局并发上限
    async with _diagnosis_semaphore:
        try:
            logger.info("Worker '%s': processing msg_id=%s report_id=%s", worker_id, msg_id, payload.report_id)
            await _process_one_message(payload)
            # 处理成功，ACK 确认
            await asyncio.to_thread(client.xack, REDIS_STREAM_DIAGNOSIS_TRIGGER, REDIS_STREAM_DIAGNOSIS_GROUP, msg_id)
            logger.info("Worker '%s': ACK msg_id=%s", worker_id, msg_id)
        except Exception as e:
            # 处理失败，不 ACK，消息留在 PEL，记录告警
            logger.error(
                "Worker '%s': failed to process msg_id=%s report_id=%s — %s",
                worker_id, msg_id, payload.report_id, e,
                exc_info=True,
            )


async def _claim_stale_messages(client, worker_id: str):
    """Claim server-accepted messages abandoned by a failed or dead consumer."""
    result = await asyncio.to_thread(
        client.xautoclaim,
        REDIS_STREAM_DIAGNOSIS_TRIGGER,
        REDIS_STREAM_DIAGNOSIS_GROUP,
        worker_id,
        PENDING_MIN_IDLE_MS,
        "0-0",
        count=WORKER_BATCH_SIZE,
    )
    return result[1] if result and len(result) > 1 else []


async def run_stream_worker(worker_id: str) -> None:
    """
    单个 Stream Consumer Worker 的主循环。

    每次拉取一批消息后，通过 asyncio.gather 并发处理，batch 内各消息互相独立。
    全局 Semaphore 保证总并发不超过 MAX_CONCURRENT_DIAGNOSES。
    """
    logger.debug("Stream worker '%s' started.", worker_id)
    client = _create_worker_redis()  # 独立连接，不复用全局 redis_manager
    last_pending_scan = 0.0

    while True:
        try:
            results = []
            now = time.monotonic()
            if now - last_pending_scan >= PENDING_SCAN_INTERVAL_SECONDS:
                stale_messages = await _claim_stale_messages(client, worker_id)
                results = (
                    [(REDIS_STREAM_DIAGNOSIS_TRIGGER, stale_messages)]
                    if stale_messages
                    else []
                )
                last_pending_scan = now

            if not results:
                # xreadgroup 是阻塞调用，放入线程池避免阻塞 event loop
                results = await asyncio.to_thread(
                    client.xreadgroup,
                    REDIS_STREAM_DIAGNOSIS_GROUP,
                    worker_id,
                    {REDIS_STREAM_DIAGNOSIS_TRIGGER: ">"},   # ">" 表示只读取未分配给任何 consumer 的新消息
                    count=WORKER_BATCH_SIZE,
                    block=BLOCK_MS,
                )
                if not results:
                    continue

            # results 格式: [(stream_name, [(msg_id, {field: value}), ...])]
            for _stream_name, messages in results:
                # 并发处理 batch 内所有消息，各消息独立 ACK，互不干扰
                await asyncio.gather(
                    *[
                        _handle_single_message(worker_id, client, msg_id, fields)
                        for msg_id, fields in messages
                    ],
                    return_exceptions=True,  # 单条失败不影响其他消息
                )

        except asyncio.CancelledError:
            logger.info("Stream worker '%s' cancelled, shutting down.", worker_id)
            break
        except Exception as e:
            logger.error("Stream worker '%s': unexpected error in main loop — %s", worker_id, e, exc_info=True)
            # 短暂等待后重试，避免错误风暴
            await asyncio.sleep(5)
