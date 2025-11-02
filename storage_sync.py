# storage_sync.py
from __future__ import annotations
import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

AZURE_BLOB_CONN_STR = os.getenv("AZURE_BLOB_CONNECTION_STRING")

_blob_service: BlobServiceClient | None = None

def _client() -> BlobServiceClient:
    global _blob_service
    if _blob_service is None:
        if not AZURE_BLOB_CONN_STR:
            raise RuntimeError("AZURE_BLOB_CONNECTION_STRING not set")
        _blob_service = BlobServiceClient.from_connection_string(AZURE_BLOB_CONN_STR)
    return _blob_service

def upload_bytes(container: str, blob_name: str, data: bytes, content_type: Optional[str] = None) -> str:
    svc = _client()
    container_client = svc.get_container_client(container)
    try:
        container_client.create_container()
    except Exception:
        pass
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(data, overwrite=True, content_type=content_type)
    return f"{container}/{blob_name}"

def download_bytes(container: str, blob_name: str) -> bytes:
    svc = _client()
    blob_client = svc.get_blob_client(container, blob_name)
    return blob_client.download_blob().readall()

def upload_json(container: str, blob_name: str, payload: Dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return upload_bytes(container, blob_name, data, content_type="application/json")

def blob_sas_url(container: str, blob_name: str, minutes: int = 60) -> str:
    svc = _client()
    url = svc.get_blob_client(container, blob_name).url
    # If using account key, generate SAS; if AAD without key, return bare URL and serve via your app/CDN
    try:
        # Try to get account key (only available when using connection string with key)
        account_key = svc.credential.account_key  # type: ignore[attr-defined]
    except Exception:
        account_key = None

    if not account_key:
        return url  # fallback (no SAS)

    sas = generate_blob_sas(
        account_name=svc.account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=minutes),
    )
    return f"{url}?{sas}"
