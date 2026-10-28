import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.database import (
    attendance_collection,
    employees_collection,
    notifications_collection,
)
from app.services.email_service import send_daily_violation_email

logger = logging.getLogger(__name__)


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


@celery_app.task(name="attendance_tasks.check_daily_attendance_violations")
def check_daily_attendance_violations() -> dict:
    """
    Check weekday attendance after 6 PM India time.
    Queue an email when an employee has fewer than 5 completed hours.
    """
    company_tz = ZoneInfo(settings.company_timezone)
    today = datetime.now(company_tz).date()
    date_key = today.isoformat()

    # Monday=0 through Friday=4. Never check weekends.
    if today.weekday() >= 5:
        return {"message": "Weekend; no daily check performed."}

    checked = 0
    queued = 0
    skipped_open_sessions = 0

    employees = employees_collection.find({"is_active": True})

    for employee in employees:
        tenant_id = employee.get("tenant_id")
        employee_id = employee.get("employee_id")

        if not tenant_id or not employee_id:
            continue

        checked += 1

        record = attendance_collection.find_one(
            {
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "date": date_key,
            }
        )

        # No attendance record means zero hours for this weekday.
        if record is None:
            total_hours = 0.0
        else:
            sessions = record.get("sessions")

            if sessions is None:
                # Support older records using entry_time/exit_time.
                entry = record.get("entry_time")
                exit_time = record.get("exit_time")

                if entry is not None and exit_time is not None:
                    total_hours = round(
                        (exit_time - entry).total_seconds() / 3600,
                        2,
                    )
                elif entry is not None and exit_time is None:
                    skipped_open_sessions += 1
                    continue
                else:
                    total_hours = float(record.get("total_hours") or 0)
            else:
                # Don't evaluate a day while a session remains open.
                if any(s.get("exit_time") is None for s in sessions):
                    skipped_open_sessions += 1
                    continue

                total_seconds = sum(
                    (s["exit_time"] - s["entry_time"]).total_seconds()
                    for s in sessions
                    if s.get("entry_time") is not None
                    and s.get("exit_time") is not None
                )
                total_hours = round(total_seconds / 3600, 2)

        if total_hours >= 5:
            continue

        # This is a preliminary duplicate guard.
        # We will make it atomic in the next step before enabling the schedule.

        # Claim this notification before queueing the email.
        # The unique MongoDB index prevents duplicate claims.
        try:
            notifications_collection.insert_one(
                {
                    "tenant_id": tenant_id,
                    "employee_id": employee_id,
                    "period_start": date_key,
                    "period_end": date_key,
                    "violation_type": "daily_hours",
                    "total_hours": total_hours,
                    "status": "queued",
                    "created_at": datetime.now(ZoneInfo("UTC")),
                }
            )
        except DuplicateKeyError:
            # This employee's daily notification was already claimed.
            continue

        try:
            send_daily_violation_email_task.delay(
                employee_name=employee.get("name", employee_id),
                employee_email=employee["email"],
                attendance_date=date_key,
                total_hours=total_hours,
                tenant_id=tenant_id,
            )
            queued += 1

        except Exception:
            logger.exception(
                "Could not queue daily violation email for employee %s",
                employee_id,
            )
            notifications_collection.update_one(
                {
                    "tenant_id": tenant_id,
                    "employee_id": employee_id,
                    "period_start": date_key,
                    "period_end": date_key,
                    "violation_type": "daily_hours",
                },
                {
                    "$set": {
                        "status": "queue_failed",
                        "updated_at": datetime.now(ZoneInfo("UTC")),
                    }
                },
            )

    return {
        "date": date_key,
        "employees_checked": checked,
        "emails_queued": queued,
        "open_sessions_skipped": skipped_open_sessions,
    }
