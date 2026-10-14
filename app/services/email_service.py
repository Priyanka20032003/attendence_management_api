
import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_email(
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> bool:
    if not settings.email_enabled:
        print("Email sending is disabled. Set EMAIL_ENABLED=true to send.")
        return False

    if not settings.smtp_username or not settings.smtp_password:
        raise ValueError(
            "SMTP_USERNAME and SMTP_PASSWORD must be configured."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.email_from or settings.smtp_username
    message["To"] = recipient
    message.set_content(body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=20,
        ) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(
                settings.smtp_username,
                settings.smtp_password,
            )
            server.send_message(message)

        print(f"Email sent successfully to {recipient}")
        return True

    except (smtplib.SMTPException, OSError) as exc:
        print(f"Email sending failed: {exc}")
        raise


def send_daily_violation_email(
    employee_name: str,
    employee_email: str,
    attendance_date: str,
    total_hours: float,
) -> bool:
    subject = "Attendance Policy Violation - Daily Working Hours"

    body = (
        f"Dear {employee_name},\n\n"
        "You have not met the minimum daily office attendance "
        "requirement.\n\n"
        f"Date: {attendance_date}\n"
        "Required working hours: 5\n"
        f"Recorded working hours: {total_hours}\n\n"
        "Please ensure that you comply with the office attendance policy."
    )

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>Attendance Policy Violation</h2>
        <p>Dear {employee_name},</p>
        <p>
          Your recorded office hours are below the minimum daily
          requirement. Please review the details below.
        </p>
        <table style="border-collapse: collapse; width: 100%;">
          <thead>
            <tr style="background-color: #eeeeee;">
              <th style="border: 1px solid #cccccc; padding: 10px;">
                Policy
              </th>
              <th style="border: 1px solid #cccccc; padding: 10px;">
                Required
              </th>
              <th style="border: 1px solid #cccccc; padding: 10px;">
                Actual
              </th>
              <th style="border: 1px solid #cccccc; padding: 10px;">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="border: 1px solid #cccccc; padding: 10px;">
                Daily working hours
              </td>
              <td style="border: 1px solid #cccccc; padding: 10px;">
                5 hours
              </td>
              <td style="border: 1px solid #cccccc; padding: 10px;">
                {total_hours:.2f} hours
              </td>
              <td style="border: 1px solid #cccccc; padding: 10px;
                         color: #b42318; font-weight: bold;">
                Violation
              </td>
            </tr>
            <tr>
              <td style="border: 1px solid #cccccc; padding: 10px;">
                Weekly office days
              </td>
              <td style="border: 1px solid #cccccc; padding: 10px;">
                3 days
              </td>
              <td colspan="2"
                  style="border: 1px solid #cccccc; padding: 10px;">
                Evaluated at week-end
              </td>
            </tr>
            <tr>
              <td style="border: 1px solid #cccccc; padding: 10px;">
                Weekly working hours
              </td>
              <td style="border: 1px solid #cccccc; padding: 10px;">
                15 hours
              </td>
              <td colspan="2"
                  style="border: 1px solid #cccccc; padding: 10px;">
                Evaluated at week-end
              </td>
            </tr>
          </tbody>
        </table>
        <p>
          Please ensure that you comply with the company's office
          attendance policy.
        </p>
        <p>Attendance Management System</p>
      </body>
    </html>
    """

    return send_email(
        recipient=employee_email,
        subject=subject,
        body=body,
        html_body=html_body,
    )