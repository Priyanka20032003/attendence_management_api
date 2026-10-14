from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pymongo.errors import PyMongoError

from app.api.attendance import router as attendance_router
from app.api.employees import router as employees_router
from app.api.reports import router as reports_router
from app.db.database import close_database_connection, connect_to_database


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
    return {"message": "Attendance Management API is running"}


@app.get("/health")
def health():
    from app.db.database import client

    try:
        client.admin.command("ping")

        return {
            "status": "healthy",
            "database": "connected",
        }
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database is unavailable",
        ) from exc
