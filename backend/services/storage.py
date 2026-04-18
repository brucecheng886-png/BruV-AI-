"""
MinIO 物件儲存服務
"""
import logging
from io import BytesIO

from minio import Minio
from minio.error import S3Error

from config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None


def get_minio_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
        # 確保 bucket 存在
        if not _client.bucket_exists(settings.MINIO_BUCKET):
            _client.make_bucket(settings.MINIO_BUCKET)
            logger.info("Created MinIO bucket: %s", settings.MINIO_BUCKET)
    return _client


def upload_file(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """上傳檔案至 MinIO，回傳 object_name"""
    client = get_minio_client()
    client.put_object(
        settings.MINIO_BUCKET,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    logger.info("Uploaded to MinIO: %s (%d bytes)", object_name, len(data))
    return object_name


def download_file(object_name: str) -> bytes:
    """從 MinIO 下載檔案"""
    client = get_minio_client()
    response = client.get_object(settings.MINIO_BUCKET, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_file(object_name: str):
    """從 MinIO 刪除檔案"""
    client = get_minio_client()
    try:
        client.remove_object(settings.MINIO_BUCKET, object_name)
    except S3Error as e:
        logger.warning("MinIO delete failed for %s: %s", object_name, e)
