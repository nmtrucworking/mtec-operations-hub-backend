from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Member


DEPARTMENT_LABEL_BY_CODE: dict[str, str] = {
    "BCN": "Ban Chủ nhiệm",
    "BVH": "Ban Vận hành",
    "BCNg": "Ban Công nghệ",
    "BTT": "Ban Truyền thông",
}


def _normalize_text(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )


_DEPARTMENT_CODE_BY_ALIAS: dict[str, str] = {
    "bcn": "BCN",
    "ban chu nhiem": "BCN",
    "chu nhiem": "BCN",
    "bvh": "BVH",
    "ban van hanh": "BVH",
    "van hanh": "BVH",
    "bcng": "BCNg",
    "ban cong nghe": "BCNg",
    "cong nghe": "BCNg",
    "btt": "BTT",
    "ban truyen thong": "BTT",
    "truyen thong": "BTT",
}


for code, label in DEPARTMENT_LABEL_BY_CODE.items():
    _DEPARTMENT_CODE_BY_ALIAS[_normalize_text(code)] = code
    _DEPARTMENT_CODE_BY_ALIAS[_normalize_text(label)] = code


def normalize_department_code(value: str, *, strict: bool = False) -> str | None:
    normalized = _normalize_text(value)
    code = _DEPARTMENT_CODE_BY_ALIAS.get(normalized)
    if code:
        return code
    if strict and normalized:
        raise ValueError(f"Ban khong hop le: {value}")
    return None


def normalize_department_codes(value: object, *, strict: bool = False) -> list[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        text = str(value).strip()
        if not text:
            return []
        items = [part.strip() for part in re.split(r"[,;/\n|]+", text) if part.strip()]

    normalized_codes: list[str] = []
    for item in items:
        code = normalize_department_code(str(item), strict=strict)
        if code and code not in normalized_codes:
            normalized_codes.append(code)
    return normalized_codes


def department_codes_to_labels(codes: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    labels: list[str] = []
    for code in codes:
        label = DEPARTMENT_LABEL_BY_CODE.get(code)
        if label and label not in labels:
            labels.append(label)
    return labels


def serialize_department_labels(codes: list[str] | tuple[str, ...] | set[str]) -> str | None:
    labels = department_codes_to_labels(list(codes))
    return ", ".join(labels) if labels else None


def serialize_department_codes(codes: list[str] | tuple[str, ...] | set[str]) -> str | None:
    normalized_codes = normalize_department_codes(list(codes))
    return ",".join(normalized_codes) if normalized_codes else None


def extract_member_department_codes(member: Member) -> list[str]:
    departments = getattr(member, "member_departments", None) or []
    codes = [item.department_code for item in departments if getattr(item, "department_code", None)]
    if codes:
        seen: list[str] = []
        for code in codes:
            if code not in seen:
                seen.append(code)
        return seen
    return normalize_department_codes(getattr(member, "ban", None))


def extract_member_department_labels(member: Member) -> list[str]:
    return department_codes_to_labels(extract_member_department_codes(member))


def primary_member_department_code(member: Member) -> str | None:
    codes = extract_member_department_codes(member)
    return codes[0] if codes else None


def set_member_departments(member: Member, codes: list[str]) -> None:
    from app.models import MemberDepartment

    member.member_departments = [
        MemberDepartment(department_code=code, sort_order=index)
        for index, code in enumerate(codes)
    ]
