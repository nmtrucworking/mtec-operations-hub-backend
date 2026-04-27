import os

SECRET_KEY = os.getenv("SECRET_KEY", "mtec-dev-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))

AI_GEMINI_BASE_URL = os.getenv("AI_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
AI_GEMINI_MODEL = os.getenv("AI_GEMINI_MODEL", "gemini-1.5-flash")
