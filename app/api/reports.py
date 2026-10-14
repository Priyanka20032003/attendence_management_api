import calendar
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.db.database import attendance_collection, employees_collection

router = APIRouter(
    prefix="/api/v1/attendance",
    tags=["Attendance Reports"],
)


def get_report_dates(
    report_type: str,
    report_date: date | None,
    year: int | None,
    month: int | None,
    start_date: date | None,
    end_date: date | None,
):
    if report_type == "daily":
        if not report_date:
            raise HTTPException(400, "date is required")
        return report_date, report_date

    if report_type == "weekly":
        if not report_date:
            raise HTTPException(400, "date is required")
        start = report_date - timedelta(days=report_date.weekday())
        return start, start + timedelta(days=6)

    if report_type == "monthly":
        if year is None or month is None or not 1 <= month <= 12:
            raise HTTPException(400, "Valid year and month are required")
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    if report_type == "yearly":
        if year is None:
            raise HTTPException(400, "year is required")
        return date(year, 1, 1), date(year, 12, 31)

    if report_type == "custom":
        if not start_date or not end_date:
            raise HTTPException(400, "start_date and end_date are required")
        if start_date > end_date:
            raise HTTPException(400, "start_date cannot be after end_date")
        if (end_date - start_date).days > 366:
            raise HTTPException(
                400,
                "Custom range cannot exceed 367 calendar days",
            )
        return start_date, end_date

    raise HTTPException(
        400,
        detail=("report_type must be daily, weekly, monthly, " "yearly, or custom"),
    )


@router.get("/report/")
def attendance_report(
    report_type: str = Query(
        ...,
        description="Choose: daily, weekly, monthly, yearly, or custom",
        enum=["daily", "weekly", "monthly", "yearly", "custom"],
    ),
    date_value: Annotated[
        date | None,
        Query(alias="date"),
    ] = None,
    year: int | None = None,
    month: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    start, end = get_report_dates(
        report_type,
        date_value,
        year,
        month,
        start_date,
        end_date,
    )

    employees = list(employees_collection.find({"is_active": True}, {"_id": 0}))

    records = list(
        attendance_collection.find(
            {
                "date": {
                    "$gte": start.isoformat(),
                    "$lte": end.isoformat(),
                }
            },
            {"_id": 0},
        ).sort([("date", 1), ("employee_id", 1)])
    )

    attendance_lookup = {
        (record["employee_id"], record["date"]): record for record in records
    }

    report_days = []
    current = start
    while current <= end:
        report_days.append(current)
        current += timedelta(days=1)

    employee_reports = []
    total_present_days = 0
    total_absent_days = 0
    total_incomplete = 0
    total_hours = 0.0

    for employee in employees:
        employee_id = employee["employee_id"]
        joining_date = date.fromisoformat(str(employee["joining_date"])[:10])

        daily_breakdown = []
        attended_days = 0
        absent_days = 0
        incomplete_sessions = 0
        employee_hours = 0.0

        for day in report_days:
            if day.weekday() >= 5:
                daily_breakdown.append(
                    {
                        "date": day.isoformat(),
                        "status": "Weekend",
                        "entry_time": None,
                        "exit_time": None,
                        "total_hours": 0,
                    }
                )
                continue

            if day < joining_date:
                daily_breakdown.append(
                    {
                        "date": day.isoformat(),
                        "status": "Not Joined Yet",
                        "entry_time": None,
                        "exit_time": None,
                        "total_hours": 0,
                    }
                )
                continue

            record = attendance_lookup.get((employee_id, day.isoformat()))

            if not record:
                status = "Not Attended Office"
                entry_time = None
                exit_time = None
                hours = 0
                absent_days += 1
                total_absent_days += 1
            else:
                entry_time = record.get("entry_time")
                exit_time = record.get("exit_time")
                hours = record.get("total_hours") or 0

                if entry_time and not exit_time:
                    status = "Incomplete"
                    incomplete_sessions += 1
                    total_incomplete += 1
                elif entry_time and exit_time:
                    status = "Present"
                    attended_days += 1
                    total_present_days += 1
                    employee_hours += float(hours)
                    total_hours += float(hours)
                else:
                    status = record.get("status", "Unknown")

            daily_breakdown.append(
                {
                    "date": day.isoformat(),
                    "status": status,
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "total_hours": hours,
                }
            )

        employee_reports.append(
            {
                "employee_id": employee_id,
                "name": employee["name"],
                "email": employee["email"],
                "department": employee["department"],
                "days_attended": attended_days,
                "days_not_attended": absent_days,
                "incomplete_sessions": incomplete_sessions,
                "total_recorded_hours": round(employee_hours, 2),
                "daily_breakdown": daily_breakdown,
            }
        )

    return {
        "report_type": report_type,
        "period": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "timezone": settings.company_timezone,
        },
        "summary": {
            "total_active_employees": len(employees),
            "total_present_employee_days": total_present_days,
            "total_not_attended_employee_days": total_absent_days,
            "total_incomplete_sessions": total_incomplete,
            "total_recorded_hours": round(total_hours, 2),
        },
        "employees": employee_reports,
    }
