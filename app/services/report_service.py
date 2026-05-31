"""Backward-compatible exports for legacy imports.

New code should import from the responsibility-specific services:
- app.services.member_profile_export_service
- app.services.member_evaluation_export_service
"""

from app.services.member_evaluation_export_service import generate_member_evaluation_sheet_docx
from app.services.member_profile_export_service import (
    format_date,
    generate_member_profile_docx,
    generate_members_zip,
)

<<<<<<< HEAD
# Constants for checkboxes
CHECKED = RichText('☒', font='Segoe UI Symbol')
UNCHECKED = RichText('☐', font='Segoe UI Symbol')

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "templates")
MEMBER_PROFILE_TEMPLATE_PATH = os.path.join(
    TEMPLATE_DIR, 
    "member_profile_template.docx"
)
TEMPLATE_PATH = MEMBER_PROFILE_TEMPLATE_PATH  # Backward-compatible alias
EVALUATION_SHEET_TEMPLATE_PATHS = [
    os.path.join(TEMPLATE_DIR, "member_evaluation_sheet_template.docx"),
    os.path.join(TEMPLATE_DIR, "member_evaluation_sheet_template.dotx"),
    os.path.join(TEMPLATE_DIR, "BM-MTEC-NS-03 - Phiếu đánh giá thành viên.dotx"),
=======
__all__ = [
    "format_date",
    "generate_member_profile_docx",
    "generate_members_zip",
    "generate_member_evaluation_sheet_docx",
>>>>>>> 6902784838101fe8f17da8ccbf8252f798e7e9a3
]
