import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.dependencies import require_tenant_admin
from app.db.database import (attendance_collection, employees_collection,
                             notifications_collection)
from app.schemas.attendance import CheckInRequest, CheckOutRequest
from app.tasks.attendance_tasks import send_daily_violation_email_task

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/attendance",
    tags=["Attendance"],
)

company_tz = ZoneInfo(settings.company_timezone)
MIN_DAILY_HOURS = 5


def _get_employee(tenant_id: str, employee_id: str) -> dict:
    employee = employees_collection.find_one(
        {
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "is_active": True,
        }
    )

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active employee not found in your company",
        )

    return employee


def _session_hours(sessions: list[dict]) -> float:
    """Sum only completed sessions."""
    seconds = 0.0

    for session in sessions:
        entry = session.get("entry_time")
        exit_time = session.get("exit_time")

        if entry is not None and exit_time is not None:
            seconds += (exit_time - entry).total_seconds()

    return round(seconds / 3600, 2)


def _ensure_sessions(record: dict) -> list[dict]:
    """
    Support older daily records that have entry_time/exit_time
    instead of a sessions array.
    """
    sessions = record.get("sessions")

    if sessions is not None:
        return sessions

    sessions = []

    if record.get("entry_time") is not None:
        sessions.append(
            {
                "entry_time": record["entry_time"],
                "exit_time": record.get("exit_time"),
                "total_hours": record.get("total_hours"),
            }
        )

    attendance_collection.update_one(
        {"_id": record["_id"]},
        {
            "$set": {
                "sessions": sessions,
                "updated_at": datetime.now(UTC),
            }
        },
    )

    return sessions


@router.post("/check-in", status_code=status.HTTP_201_CREATED)
def check_in(
    data: CheckInRequest,
    current_user: dict = Depends(require_tenant_admin),
):
    tenant_id = current_user["tenant_id"]
    _get_employee(tenant_id, data.employee_id)

    local_datetime = datetime.combine(
        data.attendance_date,
        data.entry_time,
        tzinfo=company_tz,
    )
    entry_utc = local_datetime.astimezone(UTC)
    now = datetime.now(UTC)
    date_key = data.attendance_date.isoformat()

    query = {
        "tenant_id": tenant_id,
        "employee_id": data.employee_id,
        "date": date_key,
    }

    record = attendance_collection.find_one(query)

    if record is None:
        # Create one daily document with its first session.
        try:
            attendance_collection.insert_one(
                {
                    **query,
                    "sessions": [
                        {
                            "entry_time": entry_utc,
                            "exit_time": None,
                            "total_hours": None,
                        }
                    ],
                    "total_hours": 0.0,
                    "status": "Incomplete",
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except DuplicateKeyError:
            # Another request may have created today's document.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Attendance is being updated. Please retry.",
            )

        return {
            "message": "Check-in recorded successfully",
            "employee_id": data.employee_id,
            "date": date_key,
            "entry_time": local_datetime.isoformat(),
            "session_number": 1,
        }

    sessions = _ensure_sessions(record)

    # Do not permit a second check-in while a session is open.
    if any(session.get("exit_time") is None for session in sessions):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You must check out of your current session first",
        )

    # Conditional update prevents adding a session if another request
    # has already opened one.
    result = attendance_collection.update_one(
        {
            **query,
            "sessions": {"$not": {"$elemMatch": {"exit_time": None}}},
        },
        {
            "$push": {
                "sessions": {
                    "entry_time": entry_utc,
                    "exit_time": None,
                    "total_hours": None,
                }
            },
            "$set": {
                "status": "Incomplete",
                "updated_at": now,
            },
        },
    )

    if result.modified_count != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance changed concurrently. Please retry.",
        )

    return {
        "message": "Check-in recorded successfully",
        "employee_id": data.employee_id,
        "date": date_key,
        "entry_time": local_datetime.isoformat(),
        "session_number": len(sessions) + 1,
    }


@router.put("/check-out")
def check_out(
    data: CheckOutRequest,
    current_user: dict = Depends(require_tenant_admin),
):
    tenant_id = current_user["tenant_id"]
    # employee = _get_employee(tenant_id, data.employee_id)

    local_datetime = datetime.combine(
        data.attendance_date,
        data.exit_time,
        tzinfo=company_tz,
    )
    exit_utc = local_datetime.astimezone(UTC)
    date_key = data.attendance_date.isoformat()

    query = {
        "tenant_id": tenant_id,
        "employee_id": data.employee_id,
        "date": date_key,
    }

    record = attendance_collection.find_one(query)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No check-in found for this employee on this date",
        )

    sessions = _ensure_sessions(record)

    open_sessions = [
        session for session in sessions if session.get("exit_time") is None
    ]

    if not open_sessions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No open check-in found. Check in before checking out.",
        )

    # Close the most recent open session.
    session = open_sessions[-1]
    entry_utc = session["entry_time"]

    if exit_utc <= entry_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exit time must be later than entry time",
        )

    duration_hours = round(
        (exit_utc - entry_utc).total_seconds() / 3600,
        2,
    )

    # Update only if that session is still open.
    result = attendance_collection.update_one(
        {
            **query,
            "sessions": {
                "$elemMatch": {
                    "entry_time": entry_utc,
                    "exit_time": None,
                }
            },
        },
        {
            "$set": {
                "sessions.$.exit_time": exit_utc,
                "sessions.$.total_hours": duration_hours,
                "updated_at": datetime.now(UTC),
            }
        },
    )

    if result.modified_count != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session changed concurrently. Fetch attendance and retry.",
        )

    # Re-read the updated daily document and calculate all completed visits.
    updated_record = attendance_collection.find_one(query)

    if updated_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found after check-out",
        )

    updated_sessions = updated_record.get("sessions", [])
    daily_total = _session_hours(updated_sessions)
    has_open_session = any(
        item.get("exit_time") is None for item in updated_sessions
    )

    attendance_collection.update_one(
        {"_id": updated_record["_id"]},
        {
            "$set": {
                "total_hours": daily_total,
                "status": ("Incomplete" if has_open_session else "Present"),
                "updated_at": datetime.now(UTC),
            }
        },
    )

    return {
        "message": "Check-out recorded successfully",
        "employee_id": data.employee_id,
        "date": date_key,
        "session_entry_time": entry_utc.astimezone(company_tz).isoformat(),
        "session_exit_time": local_datetime.isoformat(),
        "session_hours": duration_hours,
        "daily_total_hours": daily_total,
        "sessions_completed": sum(
            1 for item in updated_sessions if item.get("exit_time") is not None
        ),
        "status": "Incomplete" if has_open_session else "Present",
        "daily_minimum_hours": MIN_DAILY_HOURS,
        "daily_minimum_met": daily_total >= MIN_DAILY_HOURS,
    }


@router.post("/finalize-day")
def finalize_day(
    data: CheckOutRequest,
    current_user: dict = Depends(require_tenant_admin),
):
    """
    Call this only when the employee's day is finished.
    It evaluates the accumulated daily hours, not one session.
    """
    tenant_id = current_user["tenant_id"]
    employee = _get_employee(tenant_id, data.employee_id)
    date_key = data.attendance_date.isoformat()

    record = attendance_collection.find_one(
        {
            "tenant_id": tenant_id,
            "employee_id": data.employee_id,
            "date": date_key,
        }
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No attendance record found for this date",
        )

    sessions = _ensure_sessions(record)

    if any(session.get("exit_time") is None for session in sessions):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Check out of the open session before finalizing the day",
        )

    daily_total = _session_hours(sessions)

    email_queued = False

    if daily_total < MIN_DAILY_HOURS:
        notification = {
            "tenant_id": tenant_id,
            "employee_id": data.employee_id,
            "period_start": date_key,
            "period_end": date_key,
            "violation_type": "daily_hours",
            "total_hours": daily_total,
            "status": "queued",
            "created_at": datetime.now(UTC),
        }

        try:
            notifications_collection.insert_one(notification)
        except DuplicateKeyError:
            # The scheduled task or an earlier finalization
            # has already claimed this daily notification.
            pass
        else:
            try:
                send_daily_violation_email_task.delay(
                    employee_name=employee["name"],
                    employee_email=employee["email"],
                    attendance_date=date_key,
                    total_hours=daily_total,
                    tenant_id=tenant_id,
                )
                email_queued = True
            except Exception:
                logger.exception(
                    "Could not queue daily violation email for tenant %s",
                    tenant_id,
                )
                notifications_collection.update_one(
                    {
                        "tenant_id": tenant_id,
                        "employee_id": data.employee_id,
                        "period_start": date_key,
                        "period_end": date_key,
                        "violation_type": "daily_hours",
                    },
                    {
                        "$set": {
                            "status": "queue_failed",
                            "updated_at": datetime.now(UTC),
                        }
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Could not queue the violation email. "
                        "Please contact the administrator."
                    ),
                )

    return {
        "message": "Daily attendance evaluated",
        "employee_id": data.employee_id,
        "date": date_key,
        "total_hours": daily_total,
        "minimum_hours": MIN_DAILY_HOURS,
        "violation": daily_total < MIN_DAILY_HOURS,
        "email_queued": email_queued,
    }


@router.get("/{employee_id}")
def get_attendance(
    employee_id: str,
    current_user: dict = Depends(require_tenant_admin),
):
    tenant_id = current_user["tenant_id"]

    employee = employees_collection.find_one(
        {
            "tenant_id": tenant_id,
            "employee_id": employee_id,
        },
        {"_id": 0, "employee_id": 1},
    )

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found in your company",
        )

    records = list(
        attendance_collection.find(
            {
                "tenant_id": tenant_id,
                "employee_id": employee_id,
            },
            {"_id": 0},
        ).sort("date", -1)
    )

    for record in records:
        sessions = record.get("sessions")

        if sessions is not None:
            record["total_hours"] = _session_hours(sessions)
            record["sessions_completed"] = sum(
                1
                for session in sessions
                if session.get("exit_time") is not None
            )
            record["has_open_session"] = any(
                session.get("exit_time") is None for session in sessions
            )

    return {
        "employee_id": employee_id,
        "count": len(records),
        "attendance": records,
    }
