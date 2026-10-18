from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def reject_placeholder(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("This field cannot be empty")

    if value.casefold() in {"string", "test", "example"}:
        raise ValueError("Please replace the example value with real data")

    return value


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    employee_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    department: str = Field(min_length=1, max_length=100)
    joining_date: date

    @field_validator("employee_id", "name", "department")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        return reject_placeholder(value)


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    department: str = Field(min_length=1, max_length=100)
    joining_date: date

    @field_validator("name", "department")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        return reject_placeholder(value)


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    employee_id: str
    name: str
    email: EmailStr
    department: str
    joining_date: date
    is_active: bool
