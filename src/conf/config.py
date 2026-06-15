from pydantic import EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg://postgres:hw11secret@localhost:5433/hw11"

    # JWT — `jwt_secret` is intentionally required (no default) so the app
    # refuses to boot without a real secret in `.env`; no secret lives in code.
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_expiration_seconds: int = 3600  # 1 hour
    jwt_refresh_expiration_seconds: int = 604800  # 7 days

    # Mail (smtp.meta.ua per the Topic 11 lecture). Dev defaults so the app
    # boots without real credentials — email simply won't send until set.
    mail_username: EmailStr = "example@meta.ua"
    mail_password: str = "secretPassword"
    mail_from: EmailStr = "example@meta.ua"
    mail_port: int = 465
    mail_server: str = "smtp.meta.ua"
    mail_from_name: str = "Contacts API"
    mail_starttls: bool = False
    mail_ssl_tls: bool = True
    use_credentials: bool = True
    validate_certs: bool = True

    # Cloudinary — dev defaults; real values come from `.env`.
    cloudinary_name: str = "cloud_name"
    cloudinary_api_key: str = "api_key"
    cloudinary_api_secret: str = "api_secret"

    # CORS
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
