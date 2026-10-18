from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "attendance_management",
    broker=settings.celery_broker_url,
    include=["app.tasks.attendance_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
