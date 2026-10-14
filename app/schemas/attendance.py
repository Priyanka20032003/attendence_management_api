from datetime import date, time

from pydantic import BaseModel, Field


class CheckInRequest(BaseModel):
    employee_id: str = Field(min_length=1)
    attendance_date: date
    entry_time: time


class CheckOutRequest(BaseModel):
    employee_id: str = Field(min_length=1)
    attendance_date: date
    exit_time: time
