from contextlib import asynccontextmanager
from app.api.employees import router as employees_router
from app.api.attendance import router as attendance_router

from app.api.reports import router as reports_router

from fastapi import FastAPI, HTTPException

from app.db.database import (
    connect_to_database,
    close_database_connection,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        connect_to_database()
        yield
    finally:
        close_database_connection()


app = FastAPI(
    title="Centralized Employee Attendance Management System",
    description="Employee attendance, policy compliance, and reporting APIs",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(employees_router)
app.include_router(attendance_router)

app.include_router(reports_router)


@app.get("/")
def home():
    return {
        "message": "Attendance Management API is running"
    }


@app.get("/health")
def health():
    try:
        from app.db.database import client

        client.admin.command("ping")

        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database is unavailable",
        )