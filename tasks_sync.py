# tasks_sync.py
from __future__ import annotations
import os
import os.path as osp
from typing import Dict, Any, List
import pandas as pd  # <<< NEW
from celery import states
from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_process_init

from celery_app_sync import celery
from storage_sync import download_bytes, upload_json
from schemas import FinancialData
from ocr_pipeline_sync import (
    get_ocr_model,
    pdf_bytes_to_page_arrays,
    run_ocr,
    extract_text_from_doctr_export,
    call_llm_structured,
)

RESULTS_CONTAINER = os.getenv("AZURE_BLOB_RESULTS_CONTAINER", "results")

@worker_process_init.connect
def _warm_ocr_model(**_kwargs):
    try:
        get_ocr_model()
        print("[Worker] OCR model loaded")
    except Exception as e:
        print(f"[Worker] OCR preload failed: {e}")

def financial_data_to_df(data: Dict[str, Any]) -> pd.DataFrame:
    """
    Convert structured FinancialData (dict) into a tidy DataFrame:
    columns: Company Name | Year End Date | Category | Item | Value (£'000)
    """
    rows: List[Dict[str, Any]] = []
    if not data:
        return pd.DataFrame(columns=["Company Name", "Year End Date", "Category", "Item", "Value (£'000)"])

    company_name = data.get("company_name") or "—"
    year_end_date = data.get("year_end_date") or "—"

    # Expect sections: income_statement, balance_sheet
    for section_key in ("income_statement", "balance_sheet"):
        section = data.get(section_key) or {}
        if not isinstance(section, dict):
            continue
        for item_key, val in section.items():
            rows.append({
                "Company Name": company_name,
                "Year End Date": year_end_date,
                "Category": section_key.replace("_", " ").title(),
                "Item": item_key.replace("_", " ").title(),
                "Value (£'000)": val,
            })

    return pd.DataFrame(rows)

@celery.task(bind=True, acks_late=True, name="tasks.process_pdf")
def process_pdf(
    self,
    blob_path: str,
    dpi: int = 160,
    return_text: bool = False,
    return_table_html: bool = True,   # <<< NEW
) -> Dict[str, Any]:
    """
    blob_path: 'container/blobname.pdf'
    Downloads PDF, runs OCR + LLM, writes JSON result back to blob.
    """
    try:
        container, blob = blob_path.split("/", 1)
        pdf_bytes = download_bytes(container, blob)

        pages = pdf_bytes_to_page_arrays(pdf_bytes, dpi=dpi)
        doc_dict = run_ocr(pages)
        full_text = extract_text_from_doctr_export(doc_dict)
        if not full_text.strip():
            raise RuntimeError("OCR produced empty text")

        data = call_llm_structured(full_text, FinancialData)

        result_payload: Dict[str, Any] = {
            "financial_data": data.model_dump(),
            "pages": len(doc_dict.get("pages", [])),
        }
        if return_text:
            result_payload["ocr_text"] = full_text

        if return_table_html:
            df = financial_data_to_df(result_payload["financial_data"])
            # Clean, borderless table with a class you can target in CSS
            result_payload["table_html"] = df.to_html(index=False, border=0, classes="financial-table")

        json_name = osp.splitext(blob)[0] + ".json"
        upload_json(RESULTS_CONTAINER, json_name, result_payload)

        return {
            "status": "completed",
            "result_blob": f"{RESULTS_CONTAINER}/{json_name}",
            "pages": result_payload["pages"],
            "has_text": bool(return_text),
            "has_table_html": bool(return_table_html),
        }
    except SoftTimeLimitExceeded:
        self.update_state(state=states.FAILURE, meta={"reason": "soft_time_limit_exceeded"})
        raise
    except Exception as e:
        self.update_state(state=states.FAILURE, meta={"error": str(e)})
        raise
