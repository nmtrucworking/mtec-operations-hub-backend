import os


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(value: str) -> str:
    if not value:
        return value
    # Ensure psycopg3 driver is used for Postgres
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgresql://")

    # Add sslmode=require for Supabase if not present and not local
    if "supabase.co" in value and "sslmode" not in value:
        sep = "&" if "?" in value else "?"
        value += f"{sep}sslmode=require"
    return value


def _as_list(value: str, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _with_localhost_origins(origins: list[str]) -> list[str]:
    if "*" in origins:
        return origins

    localhost_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    merged: list[str] = []
    for origin in [*origins, *localhost_origins]:
        if origin not in merged:
            merged.append(origin)
    return merged


APP_ENV = os.getenv("APP_ENV", "development")
DATABASE_URL = normalize_database_url(
    os.getenv("DATABASE_URL", "sqlite:///./mtec_ops.db")
)
AUTO_CREATE_TABLES = _as_bool(
    os.getenv("AUTO_CREATE_TABLES"), default=(APP_ENV == "development")
)
# Disable seed data by default when running tests to avoid startup side-effects
# (tests control seeding explicitly via env var). If ENABLE_SEED_DATA is set,
# respect that value; otherwise default to False in test env, True otherwise.
ENABLE_SEED_DATA = _as_bool(os.getenv("ENABLE_SEED_DATA"), default=(APP_ENV != "test"))
CORS_ORIGINS = _with_localhost_origins(
    _as_list(os.getenv("CORS_ORIGINS", "*"), default=["*"])
)

SECRET_KEY = os.getenv("SECRET_KEY", "mtec-dev-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

DISCIPLINE_LEGACY_DEPRECATION_HEADER = _as_bool(
    os.getenv("DISCIPLINE_LEGACY_DEPRECATION_HEADER"), default=False
)
DISCIPLINE_LEGACY_READ_ONLY = _as_bool(
    os.getenv("DISCIPLINE_LEGACY_READ_ONLY"), default=False
)
EVALUATION_LEGACY_MIGRATION_ENABLED = _as_bool(
    os.getenv("EVALUATION_LEGACY_MIGRATION_ENABLED"), default=False
)
