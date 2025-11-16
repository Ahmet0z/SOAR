from functools import lru_cache
from typing import List

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    secret_key: str = Field("change-me", env="SOAR_SECRET_KEY")
    algorithm: str = Field("HS256", env="SOAR_JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(60, env="SOAR_TOKEN_EXPIRE_MINUTES")
    database_url: str = Field("sqlite:///./soar.db", env="SOAR_DATABASE_URL")
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"], env="SOAR_CORS_ORIGINS")
    default_tenant_slug: str = Field("default", env="SOAR_DEFAULT_TENANT")
    default_tenant_name: str = Field("Default Organization", env="SOAR_DEFAULT_TENANT_NAME")
    default_admin_username: str = Field("admin", env="SOAR_DEFAULT_ADMIN_USERNAME")
    default_admin_password: str = Field("admin123", env="SOAR_DEFAULT_ADMIN_PASSWORD")
    invite_expiry_hours: int = Field(168, env="SOAR_INVITE_EXPIRY_HOURS")
    redis_url: str = Field("redis://localhost:6379/0", env="SOAR_REDIS_URL")
    automation_queue_name: str = Field("automation-runs", env="SOAR_AUTOMATION_QUEUE")
    run_event_retention_days: int = Field(30, env="SOAR_RUN_EVENT_RETENTION_DAYS")
    run_event_prune_interval_minutes: int = Field(
        60, env="SOAR_RUN_EVENT_PRUNE_INTERVAL_MINUTES"
    )
    slack_webhook_url: str | None = Field(None, env="SOAR_SLACK_WEBHOOK_URL")
    teams_webhook_url: str | None = Field(None, env="SOAR_TEAMS_WEBHOOK_URL")
    smtp_host: str | None = Field(None, env="SOAR_SMTP_HOST")
    smtp_port: int = Field(587, env="SOAR_SMTP_PORT")
    smtp_username: str | None = Field(None, env="SOAR_SMTP_USERNAME")
    smtp_password: str | None = Field(None, env="SOAR_SMTP_PASSWORD")
    smtp_from: str | None = Field(None, env="SOAR_SMTP_FROM")
    smtp_use_tls: bool = Field(True, env="SOAR_SMTP_USE_TLS")
    notification_emails: List[str] = Field(
        default_factory=list, env="SOAR_NOTIFICATION_EMAILS"
    )

    @validator("notification_emails", pre=True)
    def _split_emails(cls, value):  # type: ignore[no-untyped-def]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
