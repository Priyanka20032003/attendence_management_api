import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from app.api.attendance import router as attendance_router
from app.api.auth import router as auth_router
from app.api.employees import router as employees_router
from app.api.reports import router as reports_router
from app.core.redis_client import redis_client
from app.db.database import close_database_connection, connect_to_database
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        connect_to_database()

        try:
            redis_client.ping()
            logger.info("Redis connection established")
        except RedisError:
            logger.exception("Redis is unavailable; caching may not work")

        yield
    finally:
        close_database_connection()
        redis_client.close()


app = FastAPI(
    title="Centralized Employee Attendance Management System",
    description="Employee attendance, policy compliance, and reporting APIs",
    version="1.0.0",
    lifespan=lifespan,
)
Instrumentator().instrument(app).expose(
    app,
    endpoint="/metrics",
    include_in_schema=False,
)
app.include_router(auth_router)
app.include_router(employees_router)
app.include_router(attendance_router)
app.include_router(reports_router)


@app.get("/")
def home():
    return {"message": "Attendance Management API is running"}


@app.get("/health")
def health():
    from app.db.database import client

    try:
        client.admin.command("ping")
        redis_client.ping()

        return {
            "status": "healthy",
            "database": "connected",
            "redis": "connected",
        }
    except (PyMongoError, RedisError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database or Redis is unavailable",
        ) from exc
