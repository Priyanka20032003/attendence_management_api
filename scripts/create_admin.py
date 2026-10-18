from datetime import UTC, datetime
from getpass import getpass

from pymongo.errors import PyMongoError

from app.core.security import hash_password
from app.db.database import client, tenants_collection, users_collection


def main():
    try:
        # Verify the database connection.
        client.admin.command("ping")

        tenant_name = input("Organization name: ").strip()
        tenant_id = input("Tenant ID (example: company-001): ").strip().lower()
        email = input("Administrator email: ").strip().lower()

        if not tenant_name or not tenant_id or not email:
            print("Organization name, tenant ID, and email are required.")
            return

        if users_collection.find_one({"email": email}):
            print("This email already exists. No account was created.")
            return

        if tenants_collection.find_one({"tenant_id": tenant_id}):
            print("This tenant ID already exists. No account was created.")
            return

        password = getpass("Administrator password: ")
        confirm_password = getpass("Confirm password: ")

        if len(password) < 12:
            print("Use a password with at least 12 characters.")
            return

        if password != confirm_password:
            print("Passwords do not match.")
            return

        now = datetime.now(UTC)

        tenant = {
            "tenant_id": tenant_id,
            "name": tenant_name,
            "is_active": True,
            "created_at": now,
        }

        user = {
            "email": email,
            "hashed_password": hash_password(password),
            "tenant_id": tenant_id,
            "role": "tenant_admin",
            "is_active": True,
            "created_at": now,
        }

        tenant_result = tenants_collection.insert_one(tenant)

        try:
            users_collection.insert_one(user)
        except Exception:
            # Avoid leaving an empty tenant if user creation fails.
            tenants_collection.delete_one({"_id": tenant_result.inserted_id})
            raise

        print("\nTenant and administrator created successfully.")
        print(f"Organization: {tenant_name}")
        print(f"Tenant ID: {tenant_id}")
        print(f"Administrator email: {email}")
        print("Password saved as a secure hash.")

    except PyMongoError as exc:
        print(f"Database operation failed: {exc}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
