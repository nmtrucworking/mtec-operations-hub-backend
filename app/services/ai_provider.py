import json
from urllib import error, parse, request

from app.core.config import (
    AI_API_KEY,
    AI_GEMINI_BASE_URL,
    AI_GEMINI_MODEL,
    AI_PROVIDER,
    AI_TIMEOUT_SECONDS,
)


class AIProviderError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _extract_text_from_gemini(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""

    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    chunks = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _generate_with_gemini(prompt: str, context: str | None = None) -> str:
    if not AI_API_KEY:
        raise AIProviderError(
            code="AI_PROVIDER_NOT_CONFIGURED",
            message="AI_API_KEY chua duoc cau hinh",
            status_code=503,
        )

    final_prompt = prompt.strip()
    if context:
        final_prompt = f"{final_prompt}\n\nContext:\n{context.strip()}"

    endpoint = f"{AI_GEMINI_BASE_URL}/models/{AI_GEMINI_MODEL}:generateContent"
    url = f"{endpoint}?{parse.urlencode({'key': AI_API_KEY})}"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": final_prompt,
                    }
                ]
            }
        ]
    }

    req = request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=AI_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            text = _extract_text_from_gemini(data)
            if not text:
                raise AIProviderError(
                    code="AI_EMPTY_RESPONSE",
                    message="AI tra ve noi dung rong",
                    status_code=502,
                )
            return text
    except error.HTTPError as exc:
        raise AIProviderError(
            code="AI_PROVIDER_HTTP_ERROR",
            message=f"AI provider loi HTTP: {exc.code}",
            status_code=502,
        ) from exc
    except error.URLError as exc:
        raise AIProviderError(
            code="AI_PROVIDER_UNREACHABLE",
            message="Khong the ket noi AI provider",
            status_code=502,
        ) from exc
    except TimeoutError as exc:
        raise AIProviderError(
            code="AI_PROVIDER_TIMEOUT",
            message="AI provider timeout",
            status_code=504,
        ) from exc
    except json.JSONDecodeError as exc:
        raise AIProviderError(
            code="AI_PROVIDER_INVALID_RESPONSE",
            message="AI provider tra ve du lieu khong hop le",
            status_code=502,
        ) from exc


def generate_text(prompt: str, context: str | None = None) -> tuple[str, str]:
    provider = AI_PROVIDER.lower().strip()
    if provider == "gemini":
        return _generate_with_gemini(prompt=prompt, context=context), "gemini"

    raise AIProviderError(
        code="AI_PROVIDER_UNSUPPORTED",
        message=f"Provider '{AI_PROVIDER}' chua duoc ho tro",
        status_code=500,
    )
