from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mongo_url: str = "mongodb://localhost:27017/"
    database_name: str = "attendance_management"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "amqp://guest:guest@localhost:5672//"

    company_timezone: str = "Asia/Kolkata"
    week_start_day: str = "MONDAY"

    min_office_days: int = 3
    min_weekly_hours: float = 15.0

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_enabled: bool = False

    demo_smtp_username: str = ""
    demo_smtp_password: str = ""
    demo_email_from: str = ""

    company_two_smtp_username: str = ""
    company_two_smtp_password: str = ""
    company_two_email_from: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


settings = Settings()
