from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.database import tenants_collection, users_collection

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    email = form_data.username.strip().lower()

    user = users_collection.find_one({"email": email})

    if (
        not user
        or not user.get("is_active", False)
        or not verify_password(
            form_data.password,
            user.get("hashed_password", ""),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant = tenants_collection.find_one(
        {
            "tenant_id": user.get("tenant_id"),
            "is_active": True,
        }
    )

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is inactive or unavailable",
        )

    return TokenResponse(access_token=create_access_token(str(user["_id"])))


@router.get("/me")
def read_current_user(
    current_user: dict = Depends(get_current_user),
):
    return current_user
