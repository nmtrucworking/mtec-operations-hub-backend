import os
import zipfile
from datetime import date
from io import BytesIO

from docxtpl import DocxTemplate, RichText

from app.core.departments import extract_member_department_labels
from app.models import Member, MemberSkill

CHECKED = RichText("☒", font="Segoe UI Symbol")
UNCHECKED = RichText("☐", font="Segoe UI Symbol")

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "templates")
MEMBER_PROFILE_TEMPLATE_PATH = os.path.join(TEMPLATE_DIR, "member_profile_template.docx")


def format_date(d: date | None) -> str:
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def generate_member_profile_docx(member: Member, skills: list[MemberSkill]) -> BytesIO:
    """Generate BM-MTEC-NS-07 member profile DOCX from member data."""
    if not os.path.exists(MEMBER_PROFILE_TEMPLATE_PATH):
        raise FileNotFoundError(f"Template not found at {MEMBER_PROFILE_TEMPLATE_PATH}")

    doc = DocxTemplate(MEMBER_PROFILE_TEMPLATE_PATH)

    context = {
        "ho_ten": (member.name or "").upper(),
        "gioi_tinh": member.gender or "",
        "ngay_sinh": format_date(member.dob),
        "mssv": member.mssv or "",
        "khoa": member.khoa or "",
        "chuyen_nganh": member.chuyen_nganh or "",
        "sdt": member.phone or "",
        "email": member.email or "",
        "link_fb": "",
        "muc_tieu": member.goal or "",
        "dinh_huong": member.orientation or "",
        "cam_ket_time": "",
        "vi_tri": member.role_title or "",
    }

    member_departments = set(extract_member_department_labels(member))
    known_departments = {"Ban Công nghệ", "Ban Truyền thông", "Ban Vận hành", "Ban Chủ nhiệm"}
    context["c_ban_cn"] = CHECKED if "Ban Công nghệ" in member_departments else UNCHECKED
    context["c_ban_tt"] = CHECKED if "Ban Truyền thông" in member_departments else UNCHECKED
    context["c_ban_vh"] = CHECKED if "Ban Vận hành" in member_departments else UNCHECKED
    context["c_ban_cnh"] = CHECKED if "Ban Chủ nhiệm" in member_departments else UNCHECKED
    context["c_ban_khac"] = CHECKED if member_departments.difference(known_departments) else UNCHECKED

    skill_map = {
        "tk": "Thiết kế",
        "qd": "Quay dựng",
        "ct": "Content",
        "fp": "Fanpage",
        "ca": "Chụp ảnh",
        "lt": "Lập trình",
        "mc": "MC",
        "gt": "Giao tiếp",
        "lvn": "Làm việc nhóm",
        "qltg": "thời gian",
        "st": "Sáng tạo",
        "gqvd": "vấn đề",
        "thvp": "văn phòng",
    }

    for key in skill_map.keys():
        context[f"{key}_cb"] = UNCHECKED
        context[f"{key}_tb"] = UNCHECKED
        context[f"{key}_tot"] = UNCHECKED
        context[f"{key}"] = UNCHECKED

    for skill in skills:
        found_key = None
        for key, keyword in skill_map.items():
            if keyword.lower() in (skill.name or "").lower():
                found_key = key
                break

        if found_key:
            context[found_key] = CHECKED
            level = (skill.level or "").lower()
            if "cơ bản" in level or "co ban" in level:
                context[f"{found_key}_cb"] = CHECKED
            elif "trung bình" in level or "trung binh" in level:
                context[f"{found_key}_tb"] = CHECKED
            elif "tốt" in level or "tot" in level:
                context[f"{found_key}_tot"] = CHECKED

    doc.render(context)

    target_stream = BytesIO()
    doc.save(target_stream)
    target_stream.seek(0)
    return target_stream


def generate_members_zip(members_with_skills: list[tuple[Member, list[MemberSkill]]]) -> BytesIO:
    """Generate ZIP file containing multiple BM-MTEC-NS-07 member profile DOCX files."""
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for member, skills in members_with_skills:
            try:
                docx_buffer = generate_member_profile_docx(member, skills)
                member_name = (member.name or "").replace(" ", "_")
                filename = f"HOSO_{member.mssv}_{member_name}.docx"
                zip_file.writestr(filename, docx_buffer.getvalue())
            except Exception:
                continue

    zip_buffer.seek(0)
    return zip_buffer
