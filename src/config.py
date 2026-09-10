from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Dental Clinic System configuration settings."""

    PROJECT_NAME: str = "Dental Clinic Management System"
    DATABASE_URL: str = "sqlite:///./dental_clinic.db"
    SECRET_KEY: str = "ineco-dental-super-secret-key-9999"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
