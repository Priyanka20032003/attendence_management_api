from celery import Celery
from celery.schedules import crontab

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
    beat_schedule={
        "daily-attendance-violation-check": {
            "task": "attendance_tasks.check_daily_attendance_violations",
            "schedule": crontab(
                hour=18,
                minute=0,
                day_of_week="1-5",
            ),
        },
    },
)
