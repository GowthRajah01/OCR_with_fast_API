# ocr_pipeline_sync.py
from __future__ import annotations
import os, sys
from typing import Dict, Any, List
import numpy as np
import fitz  # PyMuPDF
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import AzureChatOpenAI
from doctr.models import ocr_predictor
from langchain_core.caches import BaseCache  # ensures forward ref is resolved

# Tame CPU threads
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
try:
    import torch
    torch.set_num_threads(min(4, os.cpu_count() or 4))
except Exception:
    pass

_OCR_MODEL = None

def get_ocr_model():
    global _OCR_MODEL
    if _OCR_MODEL is None:
        try:
            _OCR_MODEL = ocr_predictor(
                det_arch="db_mobilenet_v3_large",
                reco_arch="crnn_mobilenet_v3_small",
                pretrained=True,
                assume_straight_pages=True,
                reco_bs=16,
            )
        except Exception as e:
            print(f"[OCR] pretrained load failed, fallback: {e}", file=sys.stderr)
            _OCR_MODEL = ocr_predictor(
                det_arch="db_mobilenet_v3_large",
                reco_arch="crnn_mobilenet_v3_small",
                pretrained=False,
                assume_straight_pages=True,
                reco_bs=16,
            )
    return _OCR_MODEL

def pdf_bytes_to_page_arrays(pdf_bytes: bytes, dpi: int = 180, max_long_side: int = 2200) -> List[np.ndarray]:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Invalid PDF: {e}")

    pages_np: List[np.ndarray] = []
    try:
        for page in doc:
            scale = dpi / 72.0
            w, h = page.rect.width, page.rect.height
            pxw, pxh = int(w * scale), int(h * scale)
            s = min(1.0, max_long_side / max(pxw, pxh))
            m = fitz.Matrix(scale * s, scale * s)

            pix = page.get_pixmap(matrix=m, alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if arr.shape[2] == 4:
                arr = arr[:, :, :3]
            pages_np.append(arr)
    finally:
        doc.close()

    if not pages_np:
        raise ValueError("PDF contains no pages")
    return pages_np

def run_ocr(pages_np: List[np.ndarray]) -> Dict[str, Any]:
    model = get_ocr_model()
    return model(pages_np).export()

def extract_text_from_doctr_export(doc_dict: Dict[str, Any]) -> str:
    lines: List[str] = []
    for page in doc_dict.get("pages", []):
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = [w.get("value", "") for w in line.get("words", [])]
                if words:
                    lines.append(" ".join(words))
    return "\n".join(lines)

def call_llm_structured(full_text: str, FinancialDataModel):
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    missing = [n for n, v in {
        "AZURE_OPENAI_ENDPOINT": endpoint,
        "AZURE_OPENAI_API_KEY": api_key,
        "AZURE_OPENAI_API_VERSION": api_version,
        "AZURE_OPENAI_DEPLOYMENT_NAME": deployment,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

    client = AzureChatOpenAI(
        openai_api_version=api_version,
        azure_endpoint=endpoint,
        openai_api_key=api_key,
        model_name=deployment,
        openai_api_type="azure",
        temperature=0.0,
        streaming=False,
        timeout=90,
    )
    structured_llm = client.with_structured_output(FinancialDataModel)
    messages = [
        SystemMessage(content=(
            "You are a financial extraction assistant.\n"
            "Extract the required fields from the text.\n"
            "If a value is missing, set it to null.\n"
            "Preserve number formatting exactly."
        )),
        HumanMessage(content=full_text),
    ]
    return structured_llm.invoke(messages)
