import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.dependencies import require_tenant_admin
from app.db.database import attendance_collection, employees_collection
from app.schemas.attendance import CheckInRequest, CheckOutRequest
from app.tasks.attendance_tasks import send_daily_violation_email_task

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/attendance",
    tags=["Attendance"],
)

company_tz = ZoneInfo(settings.company_timezone)


@router.post("/check-in", status_code=status.HTTP_201_CREATED)
def check_in(
    data: CheckInRequest,
    current_user: dict = Depends(require_tenant_admin),
):
    tenant_id = current_user["tenant_id"]

    employee = employees_collection.find_one(
        {
            "tenant_id": tenant_id,
            "employee_id": data.employee_id,
            "is_active": True,
        }
    )

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active employee not found in your company",
        )

    local_datetime = datetime.combine(
        data.attendance_date,
        data.entry_time,
        tzinfo=company_tz,
    )
    entry_utc = local_datetime.astimezone(UTC)
    now = datetime.now(UTC)

    try:
        attendance_collection.insert_one(
            {
                "tenant_id": tenant_id,
                "employee_id": data.employee_id,
                "date": data.attendance_date.isoformat(),
                "entry_time": entry_utc,
                "exit_time": None,
                "total_hours": None,
                "status": "Incomplete",
                "created_at": now,
                "updated_at": now,
            }
        )
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance already exists for this employee on this date",
        ) from exc

    return {
        "message": "Check-in recorded successfully",
        "employee_id": data.employee_id,
        "date": data.attendance_date.isoformat(),
        "entry_time": local_datetime.isoformat(),
    }


@router.put("/check-out")
def check_out(
    data: CheckOutRequest,
    current_user: dict = Depends(require_tenant_admin),
):
    tenant_id = current_user["tenant_id"]

    employee = employees_collection.find_one(
        {
            "tenant_id": tenant_id,
            "employee_id": data.employee_id,
            "is_active": True,
        }
    )

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active employee not found in your company",
        )

    local_datetime = datetime.combine(
        data.attendance_date,
        data.exit_time,
        tzinfo=company_tz,
    )
    exit_utc = local_datetime.astimezone(UTC)

    record = attendance_collection.find_one(
        {
            "tenant_id": tenant_id,
            "employee_id": data.employee_id,
            "date": data.attendance_date.isoformat(),
            "exit_time": None,
        }
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No open check-in found for this date",
        )

    entry_time = record["entry_time"]

    if exit_utc <= entry_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exit time must be later than entry time",
        )

    total_hours = round(
        (exit_utc - entry_time).total_seconds() / 3600,
        2,
    )

    result = attendance_collection.update_one(
        {
            "_id": record["_id"],
            "tenant_id": tenant_id,
            "exit_time": None,
        },
        {
            "$set": {
                "exit_time": exit_utc,
                "total_hours": total_hours,
                "status": "Present",
                "updated_at": datetime.now(UTC),
            }
        },
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Attendance was already updated; "
                "please fetch the record again"
            ),
        )

    # Queue an email if the employee worked less than 5 hours.
    if total_hours < 5:
        try:
            send_daily_violation_email_task.delay(
                employee_name=employee["name"],
                employee_email=employee["email"],
                attendance_date=data.attendance_date.isoformat(),
                total_hours=total_hours,
                tenant_id=tenant_id,
            )
        except Exception:
            logger.exception(
                "Could not queue daily violation email " "for tenant %s",
                tenant_id,
            )

    return {
        "message": "Check-out recorded successfully",
        "employee_id": data.employee_id,
        "date": data.attendance_date.isoformat(),
        "entry_time": entry_time.astimezone(company_tz).isoformat(),
        "exit_time": local_datetime.isoformat(),
        "total_hours": total_hours,
        "status": "Present",
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

    return {
        "employee_id": employee_id,
        "count": len(records),
        "attendance": records,
    }
