from uuid import uuid4

APPROVAL_ROLE_BY_CATEGORY = {
    "Su kien": "bvh_finance",
    "Vat tu": "bvh_finance",
    "Hoi phi": "bvh_finance",
    "Doi ngoai": "bcn",
    "Thiet bi": "bcn",
    "Du an lon": "bcn",
}


def generate_prefixed_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8].upper()}"


def get_required_approval_role(category: str) -> str:
    return APPROVAL_ROLE_BY_CATEGORY.get(category, "bvh_finance")


def sanitize_pagination(page: int, page_size: int) -> tuple[int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    return page, page_size
