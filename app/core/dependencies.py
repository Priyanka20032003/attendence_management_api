import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.db.database import tenants_collection, users_collection

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
):
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")

        if not user_id or not ObjectId.is_valid(user_id):
            raise credentials_error

    except jwt.InvalidTokenError:
        raise credentials_error

    user = users_collection.find_one({"_id": ObjectId(user_id)})

    if not user or not user.get("is_active", False):
        raise credentials_error

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

    return {
        "user_id": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "tenant_id": user["tenant_id"],
    }


def require_tenant_admin(
    current_user: dict = Depends(get_current_user),
):
    if current_user["role"] not in {
        "tenant_admin",
        "platform_admin",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )

    return current_user
