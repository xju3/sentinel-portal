import asyncio
import json
import logging

from pub.manager.database import redis_manager, minio_manager
from pub.utils.redis_keys import REDIS_STREAM_DIA_INGEST, REDIS_STREAM_DIA_GROUP
from app.preparation.payload import DeviceDiagnosticReport
from app.preparation.ingestion import process_incoming_report

logger = logging.getLogger(__name__)

# 每次从 Stream 拉取的最大消息数
WORKER_BATCH_SIZE = 5
# xreadgroup 阻塞等待时间（毫秒），避免空轮询 CPU 空转
BLOCK_MS = 2000
# 全局最大并发诊断数（所有 worker 共享），防止数据库连接被打爆
# 实际并发上限 = min(WORKER_COUNT * WORKER_BATCH_SIZE, MAX_CONCURRENT_DIAGNOSES)
MAX_CONCURRENT_DIAGNOSES = 10

# 全局信号量，在模块加载时创建
_diagnosis_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DIAGNOSES)


def _ensure_consumer_group() -> None:
    """
    确保 Stream 和 Consumer Group 存在。
    若 Stream 不存在，mkstream=True 会自动创建。
    若 Group 已存在，捕获 BUSYGROUP 异常忽略即可。
    """
    client = redis_manager.get_client()
    try:
        client.xgroup_create(
            REDIS_STREAM_DIA_INGEST,
            REDIS_STREAM_DIA_GROUP,
            id="0",          # 从最旧的消息开始消费（保证重启不丢）
            mkstream=True,
        )
        logger.info("Created consumer group '%s' on stream '%s'.", REDIS_STREAM_DIA_GROUP, REDIS_STREAM_DIA_INGEST)
    except Exception as e:
        # BUSYGROUP Consumer Group name already exists
        if "BUSYGROUP" in str(e):
            logger.debug("Consumer group '%s' already exists, skipping creation.", REDIS_STREAM_DIA_GROUP)
        else:
            raise


async def _process_one_message(bucket: str, path: str) -> None:
    """从 MinIO 拉取文件并执行完整的入库+诊断流程。"""
    minio_client = minio_manager.get_client()
    response = None
    try:
        response = await asyncio.to_thread(minio_client.get_object, bucket, path)
        file_data = await asyncio.to_thread(response.read)
        json_payload = json.loads(file_data.decode("utf-8"))
        report = DeviceDiagnosticReport.model_validate(json_payload)
        await process_incoming_report(report)
    finally:
        if response is not None:
            response.close()
            response.release_conn()


async def _handle_single_message(worker_id: str, client, msg_id: str, fields: dict) -> None:
    """
    处理单条 Stream 消息的完整生命周期：校验 → 获取信号量 → 处理 → ACK。

    每条消息独立运行，互不影响。失败时不 ACK，消息保留在 PEL。
    """
    bucket = fields.get("bucket")
    path = fields.get("path")

    if not bucket or not path:
        logger.error("Worker '%s': malformed stream message id=%s: %s", worker_id, msg_id, fields)
        # 格式错误，直接 ACK 丢弃，避免永久阻塞
        await asyncio.to_thread(client.xack, REDIS_STREAM_DIA_INGEST, REDIS_STREAM_DIA_GROUP, msg_id)
        return

    # 获取信号量：限制全局并发上限
    async with _diagnosis_semaphore:
        try:
            logger.info("Worker '%s': processing msg_id=%s bucket=%s path=%s", worker_id, msg_id, bucket, path)
            await _process_one_message(bucket, path)
            # 处理成功，ACK 确认
            await asyncio.to_thread(client.xack, REDIS_STREAM_DIA_INGEST, REDIS_STREAM_DIA_GROUP, msg_id)
            logger.info("Worker '%s': ACK msg_id=%s", worker_id, msg_id)
        except Exception as e:
            # 处理失败，不 ACK，消息留在 PEL，记录告警
            logger.error(
                "Worker '%s': failed to process msg_id=%s bucket=%s path=%s — %s",
                worker_id, msg_id, bucket, path, e,
                exc_info=True,
            )


async def run_stream_worker(worker_id: str) -> None:
    """
    单个 Stream Consumer Worker 的主循环。

    每次拉取一批消息后，通过 asyncio.gather 并发处理，batch 内各消息互相独立。
    全局 Semaphore 保证总并发不超过 MAX_CONCURRENT_DIAGNOSES。
    """
    logger.info("Stream worker '%s' started.", worker_id)
    client = redis_manager.get_client()

    while True:
        try:
            # xreadgroup 是阻塞调用，放入线程池避免阻塞 event loop
            results = await asyncio.to_thread(
                client.xreadgroup,
                REDIS_STREAM_DIA_GROUP,
                worker_id,
                {REDIS_STREAM_DIA_INGEST: ">"},   # ">" 表示只读取未分配给任何 consumer 的新消息
                count=WORKER_BATCH_SIZE,
                block=BLOCK_MS,
            )

            if not results:
                # 超时无新消息，继续循环
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
