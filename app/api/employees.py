from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

from app.db.database import employees_collection
from app.schemas.employee import EmployeeCreate, EmployeeUpdate

router = APIRouter(
    prefix="/api/v1/employees",
    tags=["Employees"],
)


@router.post("/", status_code=201)
def create_employee(employee: EmployeeCreate):
    now = datetime.now(UTC)

    document = employee.model_dump(mode="json")
    document.update(
        {
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
    )

    try:
        employees_collection.insert_one(document)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Employee ID already exists",
        )

    return {
        "message": "Employee created successfully",
        "employee": document,
    }


@router.get("/")
def get_employees():
    employees = list(
        employees_collection.find(
            {"is_active": True},
            {"_id": 0},
        )
    )

    return {
        "count": len(employees),
        "employees": employees,
    }


@router.get("/{employee_id}")
def get_employee(employee_id: str):
    employee = employees_collection.find_one(
        {"employee_id": employee_id},
        {"_id": 0},
    )

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )

    return employee


@router.put("/{employee_id}")
def update_employee(
    employee_id: str,
    employee: EmployeeUpdate,
):
    data = employee.model_dump(mode="json")
    data["updated_at"] = datetime.now(UTC)

    result = employees_collection.update_one(
        {
            "employee_id": employee_id,
            "is_active": True,
        },
        {"$set": data},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Active employee not found",
        )

    return {"message": "Employee updated successfully"}


@router.delete("/{employee_id}")
def deactivate_employee(employee_id: str):
    result = employees_collection.update_one(
        {
            "employee_id": employee_id,
            "is_active": True,
        },
        {
            "$set": {
                "is_active": False,
                "updated_at": datetime.now(UTC),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Active employee not found",
        )

    return {"message": "Employee deactivated successfully"}
