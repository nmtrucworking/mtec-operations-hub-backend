import os
from datetime import date
from io import BytesIO
from docxtpl import DocxTemplate, RichText
from app.models import Member, MemberSkill

# Constants for checkboxes
CHECKED = RichText('☒', font='Segoe UI Symbol')
UNCHECKED = RichText('☐', font='Segoe UI Symbol')

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "templates", "member_profile_template.docx")

def format_date(d: date | None) -> str:
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")

def generate_member_profile_docx(member: Member, skills: list[MemberSkill]) -> BytesIO:
    """
    Generates a DOCX profile for a member using a template.
    """
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Template not found at {TEMPLATE_PATH}")

    doc = DocxTemplate(TEMPLATE_PATH)

    # Prepare context
    context = {
        "ho_ten": (member.name or "").upper(),
        "gioi_tinh": member.gender or "",
        "ngay_sinh": format_date(member.dob),
        "mssv": member.mssv or "",
        "khoa": member.khoa or "",
        "chuyen_nganh": member.chuyen_nganh or "",
        "sdt": member.phone or "",
        "email": member.email or "",
        "link_fb": "",  # Link FB is not in our Member model yet, adding as placeholder
        "muc_tieu": member.goal or "",
        "dinh_huong": member.orientation or "",
        "cam_ket_time": "", # Placeholder
        "vi_tri": member.role_title or "",
    }

    # Handle Ban checkboxes
    context["c_ban_cn"] = CHECKED if member.ban == "Ban Công nghệ" else UNCHECKED
    context["c_ban_tt"] = CHECKED if member.ban == "Ban Truyền thông" else UNCHECKED
    context["c_ban_vh"] = CHECKED if member.ban == "Ban Vận hành" else UNCHECKED
    context["c_ban_cnh"] = CHECKED if member.ban == "Ban Chủ nhiệm" else UNCHECKED
    context["c_ban_khac"] = UNCHECKED # Default to unchecked if not one of the above

    # Skill keywords mapping from MTEC_App.py
    skill_map = {
        'tk': 'Thiết kế', 'qd': 'Quay dựng', 'ct': 'Content', 
        'fp': 'Fanpage', 'ca': 'Chụp ảnh', 'lt': 'Lập trình', 'mc': 'MC',
        'gt': 'Giao tiếp', 'lvn': 'Làm việc nhóm', 'qltg': 'thời gian',
        'st': 'Sáng tạo', 'gqvd': 'vấn đề', 'thvp': 'văn phòng'
    }

    # Initialize all skill fields to UNCHECKED
    for key in skill_map.keys():
        context[f"{key}_cb"] = UNCHECKED
        context[f"{key}_tb"] = UNCHECKED
        context[f"{key}_tot"] = UNCHECKED
        context[f"{key}"] = UNCHECKED

    # Fill in skills from database
    for skill in skills:
        # Try to find which key this skill belongs to
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

    # Render document
    doc.render(context)
    
    # Save to buffer
    target_stream = BytesIO()
    doc.save(target_stream)
    target_stream.seek(0)
    
    return target_stream
