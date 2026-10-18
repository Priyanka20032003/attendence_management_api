import json
import logging
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pymongo.errors import DuplicateKeyError
from redis.exceptions import RedisError

from app.core.dependencies import require_tenant_admin
from app.core.idempotency import execute_idempotently
from app.core.redis_client import redis_client
from app.db.database import employees_collection
from app.schemas.employee import EmployeeCreate, EmployeeUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/employees",
    tags=["Employees"],
)

CACHE_TTL_SECONDS = 300


def employee_cache_key(tenant_id: str, employee_id: str) -> str:
    return f"employees:{tenant_id}:employee:{employee_id}"


def employee_list_cache_key(tenant_id: str) -> str:
    return f"employees:{tenant_id}:list"


def get_cached_json(cache_key: str):
    try:
        cached_value = cast(
            str | None,
            redis_client.get(cache_key),
        )
        if cached_value is not None:
            return json.loads(cached_value)
    except (RedisError, json.JSONDecodeError):
        logger.warning(
            "Redis cache read failed for key %s",
            cache_key,
            exc_info=True,
        )

    return None


def set_cached_json(cache_key: str, value) -> None:
    try:
        redis_client.setex(
            cache_key,
            CACHE_TTL_SECONDS,
            json.dumps(jsonable_encoder(value)),
        )
    except (RedisError, TypeError, ValueError):
        logger.warning(
            "Redis cache write failed for key %s",
            cache_key,
            exc_info=True,
        )


def invalidate_employee_cache(
    tenant_id: str,
    employee_id: str | None = None,
) -> None:
    keys = [employee_list_cache_key(tenant_id)]

    if employee_id is not None:
        keys.append(employee_cache_key(tenant_id, employee_id))

    try:
        redis_client.delete(*keys)
    except RedisError:
        logger.warning(
            "Redis cache invalidation failed for tenant %s",
            tenant_id,
            exc_info=True,
        )


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_employee(
    employee: EmployeeCreate,
    current_user: dict = Depends(require_tenant_admin),
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
    ),
):
    tenant_id = current_user["tenant_id"]

    def create_action():
        now = datetime.now(UTC)

        document = employee.model_dump(mode="json")
        document.update(
            {
                "tenant_id": tenant_id,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        try:
            employees_collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("This employee ID already exists in your company"),
            ) from exc

        invalidate_employee_cache(
            tenant_id,
            document["employee_id"],
        )

        return {
            "message": "Employee created successfully",
            "employee": document,
        }

    return execute_idempotently(
        tenant_id=tenant_id,
        operation="create_employee",
        idempotency_key=idempotency_key,
        request_payload=employee.model_dump(mode="json"),
        action=create_action,
    )


@router.get("/")
def get_employees(
    current_user: dict = Depends(require_tenant_admin),
):
    tenant_id = current_user["tenant_id"]
    cache_key = employee_list_cache_key(tenant_id)

    cached_employees = get_cached_json(cache_key)

    if cached_employees is not None:
        return {
            "count": len(cached_employees),
            "employees": cached_employees,
        }

    employees = list(
        employees_collection.find(
            {
                "tenant_id": tenant_id,
                "is_active": True,
            },
            {"_id": 0},
        )
    )

    set_cached_json(cache_key, employees)

    return {
        "count": len(employees),
        "employees": employees,
    }


@router.get("/{employee_id}")
def get_employee(
    employee_id: str,
    current_user: dict = Depends(require_tenant_admin),
):
    tenant_id = current_user["tenant_id"]
    cache_key = employee_cache_key(tenant_id, employee_id)

    cached_employee = get_cached_json(cache_key)

    if cached_employee is not None:
        return cached_employee

    employee = employees_collection.find_one(
        {
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "is_active": True,
        },
        {"_id": 0},
    )

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active employee not found",
        )

    set_cached_json(cache_key, employee)

    return employee


@router.put("/{employee_id}")
def update_employee(
    employee_id: str,
    employee: EmployeeUpdate,
    current_user: dict = Depends(require_tenant_admin),
):
    tenant_id = current_user["tenant_id"]

    data = employee.model_dump(
        mode="json",
        exclude_unset=True,
    )
    data["updated_at"] = datetime.now(UTC)

    result = employees_collection.update_one(
        {
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "is_active": True,
        },
        {"$set": data},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active employee not found",
        )

    invalidate_employee_cache(tenant_id, employee_id)

    return {"message": "Employee updated successfully"}


@router.delete("/{employee_id}")
def deactivate_employee(
    employee_id: str,
    current_user: dict = Depends(require_tenant_admin),
):
    tenant_id = current_user["tenant_id"]

    result = employees_collection.update_one(
        {
            "tenant_id": tenant_id,
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active employee not found",
        )

    invalidate_employee_cache(tenant_id, employee_id)

    return {"message": "Employee deactivated successfully"}
