from app.db.database import attendance_collection

# Assign existing attendance records to the first company.
result = attendance_collection.update_many(
    {"tenant_id": {"$exists": False}},
    {"$set": {"tenant_id": "demo-company"}},
)

# Remove the old global unique index.
indexes = attendance_collection.index_information()

if "employee_id_1_date_1" in indexes:
    attendance_collection.drop_index("employee_id_1_date_1")

# Enforce uniqueness within each company.
attendance_collection.create_index(
    [
        ("tenant_id", 1),
        ("employee_id", 1),
        ("date", 1),
    ],
    unique=True,
)

print("Attendance migration completed.")
print("Existing records assigned:", result.modified_count)
print("Attendance indexes:", attendance_collection.index_information())
