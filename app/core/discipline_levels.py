from __future__ import annotations

import unicodedata


DISCIPLINE_LEVEL_NONE = "NONE"
DISCIPLINE_LEVEL_REMINDER = "REMINDER"
DISCIPLINE_LEVEL_WARNING_1 = "WARNING_1"
DISCIPLINE_LEVEL_WARNING_2 = "WARNING_2"
DISCIPLINE_LEVEL_SUSPENSION = "SUSPENSION"
DISCIPLINE_LEVEL_EXPULSION = "EXPULSION"

DISCIPLINE_LEVELS = {
    DISCIPLINE_LEVEL_NONE,
    DISCIPLINE_LEVEL_REMINDER,
    DISCIPLINE_LEVEL_WARNING_1,
    DISCIPLINE_LEVEL_WARNING_2,
    DISCIPLINE_LEVEL_SUSPENSION,
    DISCIPLINE_LEVEL_EXPULSION,
}

DISCIPLINE_LEVEL_LABELS = {
    DISCIPLINE_LEVEL_NONE: "Không kỷ luật",
    DISCIPLINE_LEVEL_REMINDER: "Nhắc nhở",
    DISCIPLINE_LEVEL_WARNING_1: "Cảnh cáo lần 1",
    DISCIPLINE_LEVEL_WARNING_2: "Cảnh cáo lần 2",
    DISCIPLINE_LEVEL_SUSPENSION: "Đình chỉ",
    DISCIPLINE_LEVEL_EXPULSION: "Khai trừ",
}

_ALIASES = {
    DISCIPLINE_LEVEL_NONE: {
        "",
        "không",
        "không kỷ luật",
        "khong",
        "khong ky luat",
        "none",
        "no discipline",
        "n/a",
        "na",
    },
    DISCIPLINE_LEVEL_REMINDER: {
        "nhắc nhở",
        "nhac nho",
        "reminder",
    },
    DISCIPLINE_LEVEL_WARNING_1: {
        "cảnh cáo",
        "cảnh cáo lần 1",
        "canh cao",
        "canh cao lan 1",
        "warning",
        "warning 1",
        "warning_1",
    },
    DISCIPLINE_LEVEL_WARNING_2: {
        "cảnh cáo lần 2",
        "canh cao lan 2",
        "warning 2",
        "warning_2",
    },
    DISCIPLINE_LEVEL_SUSPENSION: {
        "đình chỉ",
        "tạm đình chỉ",
        "dinh chi",
        "suspension",
        "tam dinh chi",
    },
    DISCIPLINE_LEVEL_EXPULSION: {
        "khai trừ",
        "loại khỏi clb",
        "khai tru",
        "expulsion",
        "loai khoi clb",
    },
}

def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value).strip())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(ascii_text.replace("_", " ").replace("-", " ").lower().split())


_CANONICAL_BY_NORMALIZED = {
    normalize_text(alias): canonical
    for canonical, aliases in _ALIASES.items()
    for alias in aliases
}


def normalize_discipline_level(value: str | None) -> str:
    normalized = normalize_text(value)
    upper_value = str(value or "").strip().upper()
    if upper_value in DISCIPLINE_LEVELS:
        return upper_value
    if normalized in _CANONICAL_BY_NORMALIZED:
        return _CANONICAL_BY_NORMALIZED[normalized]
    raise ValueError(f"Unsupported discipline level: {value}")


def is_none_discipline_level(value: str | None) -> bool:
    try:
        return normalize_discipline_level(value) == DISCIPLINE_LEVEL_NONE
    except ValueError:
        return False


def discipline_level_aliases(level: str) -> set[str]:
    canonical = normalize_discipline_level(level)
    aliases = {canonical, canonical.lower(), DISCIPLINE_LEVEL_LABELS[canonical]}
    aliases.update(_ALIASES[canonical])
    aliases.update({normalize_text(alias) for alias in aliases})
    return aliases


def no_discipline_level_aliases() -> set[str]:
    return discipline_level_aliases(DISCIPLINE_LEVEL_NONE)
