from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmployeeCreate(BaseModel):
    employee_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    email: EmailStr
    department: str = Field(min_length=1)
    joining_date: date


class EmployeeUpdate(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    department: str = Field(min_length=1)
    joining_date: date


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    employee_id: str
    name: str
    email: EmailStr
    department: str
    joining_date: date
    is_active: bool
