from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import settings

# client = MongoClient(settings.mongo_url, serverSelectionTimeoutMS=5000, tz_aware=True)

# database = client[settings.database_name]

client: MongoClient = MongoClient(
    settings.mongo_url,
    serverSelectionTimeoutMS=5000,
    tz_aware=True,
)

database: Database = client[settings.database_name]

employees_collection = database["employees"]
attendance_collection = database["attendance"]
notifications_collection = database["email_notifications"]


def connect_to_database():
    client.admin.command("ping")

    employees_collection.create_index(
        "employee_id",
        unique=True,
    )

    attendance_collection.create_index(
        [("employee_id", 1), ("date", 1)],
        unique=True,
    )

    attendance_collection.create_index("date")

    notifications_collection.create_index(
        [
            ("employee_id", 1),
            ("period_start", 1),
            ("period_end", 1),
            ("violation_type", 1),
        ],
        unique=True,
    )


def close_database_connection():
    client.close()
