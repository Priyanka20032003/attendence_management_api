from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.db.database import employees_collection, attendance_collection
from app.schemas.attendance import CheckInRequest, CheckOutRequest
from app.services.email_service import send_daily_violation_email

from app.core.config import settings
from app.db.database import (
    employees_collection,
    attendance_collection,
)
from app.schemas.attendance import (
    CheckInRequest,
    CheckOutRequest,
)

router = APIRouter(
    prefix="/api/v1/attendance",
    tags=["Attendance"],
)


company_tz = ZoneInfo(settings.company_timezone)


@router.post("/check-in", status_code=201)
def check_in(data: CheckInRequest):
    employee = employees_collection.find_one({
        "employee_id": data.employee_id,
        "is_active": True,
    })

    if not employee:
        raise HTTPException(404, "Active employee not found")

    local_datetime = datetime.combine(
        data.attendance_date,
        data.entry_time,
        tzinfo=company_tz,
    )
    entry_utc = local_datetime.astimezone(timezone.utc)

    try:
        attendance_collection.insert_one({
            "employee_id": data.employee_id,
            "date": data.attendance_date.isoformat(),
            "entry_time": entry_utc,
            "exit_time": None,
            "total_hours": None,
            "status": "Incomplete",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
    except DuplicateKeyError:
        raise HTTPException(
            409,
            "Attendance already exists for this employee on this date",
        )

    return {
        "message": "Check-in recorded successfully",
        "employee_id": data.employee_id,
        "date": data.attendance_date.isoformat(),
        "entry_time": local_datetime.isoformat(),
    }


@router.put("/check-out")
def check_out(data: CheckOutRequest):
    employee = employees_collection.find_one({
        "employee_id": data.employee_id,
        "is_active": True,
    })

    if not employee:
        raise HTTPException(404, "Active employee not found")

    local_datetime = datetime.combine(
        data.attendance_date,
        data.exit_time,
        tzinfo=company_tz,
    )
    exit_utc = local_datetime.astimezone(timezone.utc)

    record = attendance_collection.find_one({
        "employee_id": data.employee_id,
        "date": data.attendance_date.isoformat(),
        "exit_time": None,
    })

    if not record:
        raise HTTPException(404, "No open check-in found for this date")

    entry_time = record["entry_time"]

    if exit_utc <= entry_time:
        raise HTTPException(
            400,
            "Exit time must be later than entry time",
        )

    total_hours = round(
        (exit_utc - entry_time).total_seconds() / 3600,
        2,
    )

    attendance_collection.update_one(
        {"_id": record["_id"], "exit_time": None},
        {
            "$set": {
                "exit_time": exit_utc,
                "total_hours": total_hours,
                "status": "Present",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    
    # Send an email if the employee worked less than 5 hours.
    if total_hours < 5:
        try:
            send_daily_violation_email(
                employee_name=employee["name"],
                employee_email=employee["email"],
                attendance_date=data.attendance_date.isoformat(),
                total_hours=total_hours,
            )
        except Exception as exc:
            print(f"Could not send daily violation email: {exc}")

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
def get_attendance(employee_id: str):
    records = list(
        attendance_collection.find(
            {"employee_id": employee_id},
            {"_id": 0},
        ).sort("date", -1)
    )

    return {
        "employee_id": employee_id,
        "count": len(records),
        "attendance": records,
    }