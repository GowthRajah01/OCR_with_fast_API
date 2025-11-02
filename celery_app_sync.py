# celery_app_sync.py
from __future__ import annotations
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "kyc_ocr",
    broker=REDIS_URL,
    backend=os.getenv("CELERY_RESULT_BACKEND", REDIS_URL),
    include=["tasks_sync"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    worker_prefetch_multiplier=1,  # better for big tasks
    task_acks_late=True,
    task_time_limit=60 * 25,       # hard limit 25m
    task_soft_time_limit=60 * 20,  # soft limit 20m
)
