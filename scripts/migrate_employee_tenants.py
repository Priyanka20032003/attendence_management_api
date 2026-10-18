
from app.db.database import employees_collection

# Assign existing unassigned employee records to the first company.
result = employees_collection.update_many(
    {"tenant_id": {"$exists": False}},
    {"$set": {"tenant_id": "demo-company"}},
)

# Remove the old global unique index if it exists.
indexes = employees_collection.index_information()

if "employee_id_1" in indexes:
    employees_collection.drop_index("employee_id_1")

# Create uniqueness within each company.
employees_collection.create_index(
    [
        ("tenant_id", 1),
        ("employee_id", 1),
    ],
    unique=True,
)

print("Migration completed.")
print("Existing employees assigned:", result.modified_count)
print("Employee indexes:", employees_collection.index_information())
