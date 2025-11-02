# storage_async.py
from __future__ import annotations
import os
from typing import Optional
from azure.storage.blob.aio import BlobServiceClient

AZURE_BLOB_CONN_STR = os.getenv("AZURE_BLOB_CONNECTION_STRING")

_blob_service: BlobServiceClient | None = None

async def _client() -> BlobServiceClient:
    global _blob_service
    if _blob_service is None:
        if not AZURE_BLOB_CONN_STR:
            raise RuntimeError("AZURE_BLOB_CONNECTION_STRING not set")
        _blob_service = BlobServiceClient.from_connection_string(AZURE_BLOB_CONN_STR)
    return _blob_service

async def upload_bytes_async(container: str, blob_name: str, data: bytes, content_type: Optional[str] = None) -> str:
    svc = await _client()
    container_client = svc.get_container_client(container)
    try:
        await container_client.create_container()
    except Exception:
        pass
    blob_client = container_client.get_blob_client(blob_name)
    await blob_client.upload_blob(data, overwrite=True, content_type=content_type)
    return f"{container}/{blob_name}"
