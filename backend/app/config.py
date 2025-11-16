from functools import lru_cache
from typing import List

from pydantic import BaseSettings, Field


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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
