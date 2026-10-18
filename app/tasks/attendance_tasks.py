from app.core.celery_app import celery_app
from app.services.email_service import send_daily_violation_email


@celery_app.task(name="attendance_tasks.test_task")
def test_task(message: str) -> str:
    """Simple task to verify Celery and RabbitMQ."""
    result = f"Celery task executed successfully: {message}"
    print(result)
    return result


@celery_app.task(
    bind=True,
    name="attendance_tasks.send_daily_violation_email_task",
    max_retries=3,
    default_retry_delay=30,
)
def send_daily_violation_email_task(
    self,
    employee_name: str,
    employee_email: str,
    attendance_date: str,
    total_hours: float,
    tenant_id: str,
) -> None:
    """Send a daily attendance violation email in the background."""
    try:
        send_daily_violation_email(
            employee_name=employee_name,
            employee_email=employee_email,
            attendance_date=attendance_date,
            total_hours=total_hours,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        raise self.retry(exc=exc) from exc
