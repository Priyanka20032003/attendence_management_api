from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import settings

client: MongoClient = MongoClient(
    settings.mongo_url,
    serverSelectionTimeoutMS=5000,
    tz_aware=True,
)

database: Database = client[settings.database_name]

# Existing collections
employees_collection = database["employees"]
attendance_collection = database["attendance"]
notifications_collection = database["email_notifications"]

# New collections for authentication and multi-tenancy
users_collection = database["users"]
tenants_collection = database["tenants"]


def connect_to_database():
    client.admin.command("ping")

    # Authentication indexes
    users_collection.create_index(
        "email",
        unique=True,
    )

    tenants_collection.create_index(
        "tenant_id",
        unique=True,
    )

    # Existing indexes — retained for now
    employees_collection.create_index(
        [
            ("tenant_id", 1),
            ("employee_id", 1),
        ],
        unique=True,
    )

    attendance_collection.create_index(
        [
            ("tenant_id", 1),
            ("employee_id", 1),
            ("date", 1),
        ],
        unique=True,
    )

    attendance_collection.create_index("date")

    notifications_collection.drop_index(
    "employee_id_1_period_start_1_period_end_1_violation_type_1"
)

    old_index_name = (
    "employee_id_1_period_start_1_period_end_1_violation_type_1"
)

    existing_indexes = notifications_collection.index_information()

    if old_index_name in existing_indexes:
        notifications_collection.drop_index(old_index_name)

    notifications_collection.create_index(
        [
            ("tenant_id", 1),
            ("employee_id", 1),
            ("period_start", 1),
            ("period_end", 1),
            ("violation_type", 1),
        ],
        unique=True,
        name="tenant_employee_period_violation_unique",
    )




def close_database_connection():
    client.close()
