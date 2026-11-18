"""Application settings, read from environment / .env. Startup fails with a clear message when a required value is missing."""
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    APP_ENV: str = "development"  # development | test | production
    APP_NAME: str = "Motadata Presales Intelligence Platform"
    APP_SECRET_KEY: str
    DATABASE_URL: str
    TEST_DATABASE_URL: str = ""

    SECRETS_ENCRYPTION_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "./storage"

    EMBEDDING_PROVIDER: str = "local"  # initial value only; the admin screen is the source of truth afterwards
    EXTERNAL_EMBEDDING_API_KEY: str = ""
    MODEL_CACHE_PATH: str = "./.model_cache"

    LIBREOFFICE_PATH: str = ""
    OCR_ENGINE_PATH: str = ""

    MAX_CONCURRENT_RFP_JOBS: int = 2
    MAX_QUEUED_RFP_JOBS: int = 20
    WORKER_COUNT: int = 2

    AUTH_PROVIDER: str = "local"
    SESSION_HOURS: int = 12
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 15
    MAX_UPLOAD_MB: int = 100
    URL_FETCH_ALLOWED_DOMAINS: str = "motadata.com,docs.motadata.com"

    @property
    def storage_path(self) -> Path:
        p = Path(self.LOCAL_STORAGE_PATH)
        return p if p.is_absolute() else BACKEND_DIR / p

    @property
    def model_cache_path(self) -> Path:
        p = Path(self.MODEL_CACHE_PATH)
        return p if p.is_absolute() else BACKEND_DIR / p


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as e:
        missing = ", ".join(str(err["loc"][0]) for err in e.errors())
        raise SystemExit(f"Configuration error: missing or invalid values: {missing}. See backend/.env.example.") from None
