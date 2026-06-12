import io
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def upload_json_to_minio_sync(
    minio_client: Any,
    bucket_name: str,
    object_name: str,
    payload: Dict[str, Any],
) -> bool:
    """
    同步将字典数据作为 JSON 文件上传到 MinIO

    Args:
        minio_client: MinIO 客户端实例
        bucket_name: 存储桶名称
        object_name: 对象保存路径及名称
        payload: 需要上传的数据字典
    """
    try:
        json_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        data_stream = io.BytesIO(json_bytes)
        minio_client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data_stream,
            length=len(json_bytes),
            content_type="application/json",
        )
        logger.info(
            f"Successfully uploaded JSON data to MinIO: {bucket_name}/{object_name}"
        )
        return True
    except Exception as e:
        logger.error(
            f"Failed to upload JSON data to MinIO ({bucket_name}/{object_name}): {e}",
            exc_info=True,
        )
        return False


def download_json_from_minio_sync(
    minio_client: Any,
    bucket_name: str,
    object_name: str,
) -> Dict[str, Any]:
    """
    同步从 MinIO 下载 JSON 文件并解析为字典。

    Args:
        minio_client: MinIO 客户端实例
        bucket_name: 存储桶名称
        object_name: 对象路径及名称
    """
    response = None
    try:
        response = minio_client.get_object(
            bucket_name=bucket_name,
            object_name=object_name,
        )
        raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Downloaded JSON payload must be an object")
        logger.info(
            f"Successfully downloaded JSON data from MinIO: {bucket_name}/{object_name}"
        )
        return payload
    except Exception as e:
        logger.error(
            f"Failed to download JSON data from MinIO ({bucket_name}/{object_name}): {e}",
            exc_info=True,
        )
        raise
    finally:
        if response is not None:
            response.close()
            if hasattr(response, "release_conn"):
                response.release_conn()
