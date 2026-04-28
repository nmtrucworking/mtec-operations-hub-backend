import os


def _as_bool(value: str, default: bool = False) -> bool:
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(value: str) -> str:
	if value.startswith("postgres://"):
		return "postgresql+psycopg://" + value.removeprefix("postgres://")
	if value.startswith("postgresql://"):
		return "postgresql+psycopg://" + value.removeprefix("postgresql://")
	return value


def _as_list(value: str, default: list[str]) -> list[str]:
	if not value:
		return default
	return [item.strip() for item in value.split(",") if item.strip()]


APP_ENV = os.getenv("APP_ENV", "development")
DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./mtec_ops.db"))
AUTO_CREATE_TABLES = _as_bool(os.getenv("AUTO_CREATE_TABLES"), default=True)
# Disable seed data by default when running tests to avoid startup side-effects
# (tests control seeding explicitly via env var). If ENABLE_SEED_DATA is set,
# respect that value; otherwise default to False in test env, True otherwise.
ENABLE_SEED_DATA = (
	_as_bool(os.getenv("ENABLE_SEED_DATA"), default=(APP_ENV != "test"))
)
CORS_ORIGINS = _as_list(os.getenv("CORS_ORIGINS", "*"), default=["*"])

SECRET_KEY = os.getenv("SECRET_KEY", "mtec-dev-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))

AI_GEMINI_BASE_URL = os.getenv("AI_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
AI_GEMINI_MODEL = os.getenv("AI_GEMINI_MODEL", "gemini-1.5-flash")
