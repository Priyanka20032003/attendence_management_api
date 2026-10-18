import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any, cast

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)

IDEMPOTENCY_TTL_SECONDS = 86400  # 24 hours


def execute_idempotently(
    *,
    tenant_id: str,
    operation: str,
    idempotency_key: str,
    request_payload: dict[str, Any],
    action: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Execute an operation once per tenant, operation, and key."""

    if not idempotency_key or len(idempotency_key) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must contain 1 to 128 characters",
        )

    payload_json = json.dumps(
        request_payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    key_hash = hashlib.sha256(
        f"{tenant_id}:{operation}:{idempotency_key}".encode()
    ).hexdigest()

    redis_key = f"idempotency:{key_hash}"

    processing_record = {
        "state": "processing",
        "payload_hash": payload_hash,
    }

    try:
        claimed = redis_client.set(
            redis_key,
            json.dumps(processing_record),
            nx=True,
            ex=IDEMPOTENCY_TTL_SECONDS,
        )

        if not claimed:
            existing_value = cast(
                str | None,
                redis_client.get(redis_key),
            )
            if existing_value is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Request is being processed; please retry",
                )

            existing = json.loads(existing_value)

            if existing.get("payload_hash") != payload_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This Idempotency-Key was already used "
                        "with a different request body"
                    ),
                )

            if existing.get("state") == "completed":
                return existing["response"]

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Request is already being processed; please retry",
            )

    except HTTPException:
        raise
    except (RedisError, json.JSONDecodeError) as exc:
        logger.exception("Idempotency service unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Request deduplication is temporarily unavailable",
        ) from exc

    try:
        response = action()

        completed_record = {
            "state": "completed",
            "payload_hash": payload_hash,
            "response": response,
        }

        redis_client.set(
            redis_key,
            json.dumps(completed_record, default=str),
            ex=IDEMPOTENCY_TTL_SECONDS,
        )

        return response

    except Exception:
        try:
            # Allow a retry when the action fails.
            # Database uniqueness/conditional updates remain important.
            redis_client.delete(redis_key)
        except RedisError:
            logger.exception("Could not clear idempotency record")

        raise
