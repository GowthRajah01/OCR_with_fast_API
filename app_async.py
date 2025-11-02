# app_async.py
from __future__ import annotations
import os
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from celery.result import AsyncResult
from celery.exceptions import TimeoutError as CeleryTimeout

from celery_app_sync import celery
from tasks_sync import process_pdf
from storage_async import upload_bytes_async
from storage_sync import blob_sas_url

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)

app = FastAPI(title="PDF OCR → Financial Extractor (Async API + Sync OCR)", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_CONTAINER = os.getenv("AZURE_BLOB_CONTAINER", "uploads")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "redis": bool(os.getenv("REDIS_URL", "")),
        "blob_container": UPLOADS_CONTAINER,
    }


@app.post("/extract/batch")
async def extract_batch(
    files: List[UploadFile] = File(..., description="One or more PDF files"),
    dpi: int = Query(160, ge=100, le=400),
    return_text: bool = Query(False, description="Include raw OCR text in result blob"),
    return_table_html: bool = Query(True, description="Include HTML table built from pandas"),
    wait_seconds: int = Query(300, ge=1, le=1800, description="Max seconds to wait for all tasks"),
):
    """
    Uploads PDFs, enqueues Celery jobs for each, then waits (concurrently) up to wait_seconds
    for each job to complete and returns their payloads inline. Tasks that don't finish in time
    will return with status=timeout and include task_id/result_blob for later retrieval.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    async def store_and_enqueue(f: UploadFile) -> Dict[str, Any]:
        if f.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(status_code=400, detail=f"{f.filename}: Please upload a PDF file")

        data = await f.read()
        blob_name = f"{uuid.uuid4().hex}_{f.filename}"
        blob_path = await upload_bytes_async(
            UPLOADS_CONTAINER, blob_name, data, content_type="application/pdf"
        )

        task = process_pdf.apply_async(kwargs={
            "blob_path": blob_path,
            "dpi": dpi,
            "return_text": return_text,
            "return_table_html": return_table_html,
        })
        return {"filename": f.filename, "blob_path": blob_path, "task_id": task.id}

    submitted = await asyncio.gather(*(store_and_enqueue(f) for f in files))
    

        # wait for all tasks concurrently, but don’t block one on another
    async def wait_for(task_id: str) -> Dict[str, Any]:
        def _get():
            res: AsyncResult = AsyncResult(task_id)
            try:
                out = res.get(timeout=wait_seconds)  # blocks in a thread
                # Expect out to include "payload" (from modified Celery task)
                return {
                    "task_id": task_id,
                    "status": out.get("status", "completed"),
                    "result_blob": out.get("result_blob"),
                    "pages": out.get("pages"),
                    "has_text": out.get("has_text"),
                    "has_table_html": out.get("has_table_html"),
                    "payload": out.get("payload"),   # structured OCR payload here
                }
            except CeleryTimeout:
                # Not done in time; return minimal tracking info
                info = res.info if isinstance(res.info, dict) else None
                return {
                    "task_id": task_id,
                    "status": "timeout",
                    "result_blob": info.get("result_blob") if info else None,
                    "payload": None,
                }
            except Exception as e:
                info = res.info if isinstance(res.info, dict) else None
                return {
                    "task_id": task_id,
                    "status": "error",
                    "error": str(e),
                    "result_blob": info.get("result_blob") if info else None,
                    "payload": None,
                }

        # run blocking .get() in a thread so the event loop stays free
        return await asyncio.to_thread(_get)

    results = await asyncio.gather(*(wait_for(item["task_id"]) for item in submitted))

    return JSONResponse(content={
        "submitted": submitted,  # filenames + blob paths + task_ids
        "results": results       # each result includes the structured payload (if completed)
    })


@app.get("/tasks/{task_id}")
async def task_status(task_id: str):
    """Poll Celery task status."""
    res: AsyncResult = AsyncResult(task_id, app=celery)
    info = res.info if isinstance(res.info, dict) else {}
    payload = {
        "task_id": task_id,
        "state": res.state,
        "info": info,
        "successful": res.successful() if res.ready() else False,
        "ready": res.ready(),
    }
    return JSONResponse(content=payload)


@app.get("/results/{task_id}")
async def get_results(task_id: str, sas_minutes: int = 60):
    """Fetch result blob SAS URL once task completes."""
    res: AsyncResult = AsyncResult(task_id, app=celery)
    if not res.ready():
        raise HTTPException(status_code=202, detail="Task not finished")
    if not res.successful():
        raise HTTPException(status_code=500, detail={"state": res.state, "info": res.info})

    info = res.result or {}
    result_blob = info.get("result_blob")
    if not result_blob:
        raise HTTPException(status_code=500, detail="Result blob missing")

    container, blob = result_blob.split("/", 1)
    url = blob_sas_url(container, blob, minutes=sas_minutes)
    return JSONResponse(content={"result_blob": result_blob, "sas_url": url})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_async:app", host="0.0.0.0", port=8000, reload=True)
