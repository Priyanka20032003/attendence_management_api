import smtplib
from email.message import EmailMessage

from app.core.config import settings


def get_tenant_smtp_config(tenant_id: str) -> dict:
    if tenant_id == "demo-company":
        smtp_username = settings.demo_smtp_username
        smtp_password = settings.demo_smtp_password
        email_from = settings.demo_email_from
        company_name = "Demo Company"

    elif tenant_id == "company-two":
        smtp_username = settings.company_two_smtp_username
        smtp_password = settings.company_two_smtp_password
        email_from = settings.company_two_email_from
        company_name = "Company Two"

    else:
        raise ValueError("No email configuration found for this company.")

    if not smtp_username or not smtp_password:
        raise ValueError(f"SMTP credentials are missing for {company_name}.")

    return {
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_username": smtp_username,
        "smtp_password": smtp_password,
        "email_from": email_from or smtp_username,
        "company_name": company_name,
    }


def send_email(
    recipient: str,
    subject: str,
    body: str,
    smtp_config: dict,
    html_body: str | None = None,
) -> bool:
    if not settings.email_enabled:
        print("Email sending is disabled. Set EMAIL_ENABLED=true to send.")
        return False

    smtp_host = smtp_config["smtp_host"]
    smtp_port = smtp_config["smtp_port"]
    smtp_username = smtp_config["smtp_username"]
    smtp_password = smtp_config["smtp_password"]

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_config["email_from"]
    message["To"] = recipient
    message.set_content(body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(
            smtp_host,
            smtp_port,
            timeout=20,
        ) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_username, smtp_password)
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
    tenant_id: str,
) -> bool:
    smtp_config = get_tenant_smtp_config(tenant_id)
    company_name = smtp_config["company_name"]
    subject = (
        f"{company_name} - Attendance Policy Violation - "
        "Daily Working Hours"
    )
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
        smtp_config=smtp_config,
    )
