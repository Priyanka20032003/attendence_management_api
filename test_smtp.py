
from app.services.email_service import send_email

send_email(
    recipient="gpriyanka202003@gmail.com",
    subject="Attendance Management SMTP Test",
    body=(
        "Hello,\n\n"
        "This is a test email from the FastAPI "
        "Attendance Management System.\n\n"
        "If you received this email, Gmail SMTP is working correctly."
    ),
)