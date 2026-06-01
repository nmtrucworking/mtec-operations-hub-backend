import csv
import datetime as dt
import io
import os
import re
import unicodedata
import zipfile
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
# legacy discipline levels removed from member detail
from app.core.rbac import require_roles
from app.core.response import api_response
from app.db import get_db
from app.models import Member, User, MemberSkill, EvaluationCycle
from app.services.evaluation_calculator import EvaluationCalculatorService
from app.services.evaluation_errors import EvaluationError
from app.schemas import MemberCreate, MemberUpdate
from app.utils import sanitize_pagination
from app.services.member_profile_export_service import generate_member_profile_docx, generate_members_zip

router = APIRouter(prefix="/members", tags=["members"])


def _ascii_fallback_filename(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    normalized = unicodedata.normalize("NFKD", base)
    ascii_base = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_base = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_base).strip("._-")
    if not ascii_base:
        ascii_base = "download"
    return f"{ascii_base}{ext}"


def _attachment_content_disposition(filename: str) -> str:
    ascii_filename = _ascii_fallback_filename(filename)
    utf8_filename = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{utf8_filename}"


def _member_out(member: Member, evaluation: dict | None = None, skills: list[MemberSkill] | None = None) -> dict:
    # evaluation: optional summary from Evaluation v2 / quick review
    # legacy DisciplineRecord is deprecated; fields below will be None unless evaluation provided
    absents = None
    kpi = None
    discipline_level = None
    discipline_level_label = None
    evaluation_summary = evaluation
    if evaluation:
        absents = evaluation.get("absents")
        kpi = evaluation.get("totalScore")
        discipline_level = evaluation.get("finalClassification")
        discipline_level_label = evaluation.get("finalClassification")
    return {
        "id": member.id,
        "mssv": member.mssv,
        "name": member.name,
        "gender": member.gender,
        "dob": member.dob,
        "ban": member.ban,
        "roleTitle": member.role_title,
        "status": member.status,
        "phone": member.phone,
        "email": member.email,
        "joinDate": member.join_date,
        "lop": member.lop,
        "chuyenNganh": member.chuyen_nganh,
        "khoa": member.khoa,
        "address": member.address,
        "experience": member.experience,
        "goal": member.goal,
        "orientation": member.orientation,
        "absents": absents,
        "kpi": kpi,
        "disciplineLevel": discipline_level,
        "disciplineLevelLabel": discipline_level_label,
        "evaluationSummary": evaluation_summary,
        "createdAt": member.created_at,
        "updatedAt": member.updated_at,
        "hardSkills": [
            {"name": s.name, "level": s.level} for s in (skills or []) if s.type == "hard"
        ],
        "softSkills": [
            {"name": s.name, "level": s.level} for s in (skills or []) if s.type == "soft"
        ],
    }


def _skills_by_member(db: Session, member_ids: list[str]) -> dict[str, list[MemberSkill]]:
    if not member_ids:
        return {}
    rows = db.scalars(select(MemberSkill).where(MemberSkill.member_id.in_(member_ids))).all()
    out: dict[str, list[MemberSkill]] = {}
    for r in rows:
        out.setdefault(r.member_id, []).append(r)
    return out


def _normalize_header(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


_IMPORT_HEADER_TO_FIELD = {
    "mssv": "mssv",
    "studentid": "mssv",
    "student_id": "mssv",
    "masv": "mssv",
    "name": "name",
    "fullname": "name",
    "full_name": "name",
    "hovaten": "name",
    "gender": "gender",
    "gioitinh": "gender",
    "dob": "dob",
    "birthdate": "dob",
    "ngaysinh": "dob",
    "ban": "ban",
    "department": "ban",
    "banchuyenmon": "ban",
    "role": "roleTitle",
    "roletitle": "roleTitle",
    "chucvu": "roleTitle",
    "position": "roleTitle",
    "status": "status",
    "trangthai": "status",
    "phone": "phone",
    "phonenumber": "phone",
    "email": "email",
    "joindate": "joinDate",
    "join_date": "joinDate",
    "ngaythamgia": "joinDate",
    "lop": "lop",
    "class": "lop",
    "classname": "lop",
    "chuyennganh": "chuyenNganh",
    "major": "chuyenNganh",
    "khoa": "khoa",
    "faculty": "khoa",
    "address": "address",
    "diachi": "address",
    "experience": "experience",
    "kinhnghiem": "experience",
    "goal": "goal",
    "muctieu": "goal",
    "orientation": "orientation",
    "dinhhuong": "orientation",
}


def _parse_excel_serial_date(value: str) -> dt.date | None:
    try:
        number = float(value)
    except Exception:
        return None
    if number <= 0:
        return None
    base = dt.date(1899, 12, 30)
    try:
        return base + dt.timedelta(days=int(number))
    except Exception:
        return None


def _parse_optional_date(value: str | None) -> dt.date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    maybe_excel = _parse_excel_serial_date(text)
    if maybe_excel is not None:
        return maybe_excel
    return None


def _xlsx_to_rows(content: bytes) -> list[list[str]]:
    import xml.etree.ElementTree as ET

    def col_to_index(col: str) -> int:
        idx = 0
        for ch in col:
            if "A" <= ch <= "Z":
                idx = idx * 26 + (ord(ch) - ord("A") + 1)
        return idx

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in root.findall(".//s:si", ns):
                parts = []
                for t in si.findall(".//s:t", ns):
                    if t.text:
                        parts.append(t.text)
                shared_strings.append("".join(parts))

        sheet_path = "xl/worksheets/sheet1.xml"
        if sheet_path not in zf.namelist():
            candidates = [name for name in zf.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
            if not candidates:
                return []
            sheet_path = sorted(candidates)[0]

        sheet_root = ET.fromstring(zf.read(sheet_path))
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows: list[list[str]] = []

        for row in sheet_root.findall(".//s:sheetData/s:row", ns):
            cells: dict[int, str] = {}
            for c in row.findall("s:c", ns):
                r = c.attrib.get("r", "")
                col_letters = "".join(ch for ch in r if ch.isalpha()).upper()
                col_idx = col_to_index(col_letters)
                cell_type = c.attrib.get("t")
                value = ""
                if cell_type == "inlineStr":
                    t_node = c.find(".//s:t", ns)
                    value = (t_node.text or "") if t_node is not None else ""
                else:
                    v = c.find("s:v", ns)
                    if v is not None and v.text is not None:
                        if cell_type == "s":
                            try:
                                value = shared_strings[int(v.text)]
                            except Exception:
                                value = v.text
                        else:
                            value = v.text
                if col_idx > 0:
                    cells[col_idx] = value

            if not cells:
                continue
            max_idx = max(cells.keys())
            row_values = [cells.get(i, "") for i in range(1, max_idx + 1)]
            rows.append(row_values)

        return rows


def _records_from_csv(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    records: list[dict[str, str]] = []
    for row in reader:
        normalized: dict[str, str] = {}
        for key, value in (row or {}).items():
            if key is None:
                continue
            normalized[str(key).strip()] = "" if value is None else str(value).strip()
        if any(v for v in normalized.values()):
            records.append(normalized)
    return records


def _records_from_xlsx(content: bytes) -> list[dict[str, str]]:
    rows = _xlsx_to_rows(content)
    if not rows:
        return []
    headers = [str(h).strip() for h in rows[0]]
    records: list[dict[str, str]] = []
    for row in rows[1:]:
        if not any(str(v).strip() for v in row):
            continue
        record: dict[str, str] = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            value = row[idx] if idx < len(row) else ""
            record[header] = "" if value is None else str(value).strip()
        records.append(record)
    return records


def _map_import_record(record: dict[str, str]) -> dict:
    payload: dict[str, object] = {}
    for raw_key, raw_value in record.items():
        normalized_key = _normalize_header(raw_key)
        field = _IMPORT_HEADER_TO_FIELD.get(normalized_key)
        if not field:
            continue

        value = str(raw_value).strip()
        if value == "":
            continue

        if field in {"dob", "joinDate"}:
            parsed = _parse_optional_date(value)
            if parsed is not None:
                payload[field] = parsed
            continue

        payload[field] = value

    if "status" not in payload:
        payload["status"] = "Active"
    return payload


@router.get("/import/template")
def download_member_import_template(
    format: str = Query(default="csv"),
    _: User = Depends(require_roles("bcn", "bvh_hr")),
) -> StreamingResponse:
    if format != "csv":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chi ho tro template csv")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "mssv",
            "name",
            "gender",
            "dob",
            "ban",
            "roleTitle",
            "status",
            "phone",
            "email",
            "joinDate",
            "lop",
            "chuyenNganh",
            "khoa",
            "address",
            "experience",
            "goal",
            "orientation",
        ]
    )
    writer.writerow(
        [
            "22000001",
            "Nguyen Van A",
            "Nam",
            "2004-01-15",
            "Ban Cong nghe, Ban Truyen thong",
            "Thanh vien",
            "Active",
            "0901234567",
            "a@example.com",
            "2024-09-01",
            "D22CQCN01",
            "Khoa hoc Du lieu",
            "Cong nghe Thong tin",
            "Quan 1, TP.HCM",
            "Thuc tap FE",
            "Tham gia du an",
            "Fullstack",
        ]
    )
    buffer.seek(0)
    headers = {"Content-Disposition": "attachment; filename=members_import_template.csv"}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers=headers)


@router.post("/import")
async def import_members(
    file: UploadFile = File(...),
    on_duplicate: str = Query(default="skip", pattern="^(skip|update)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn", "bvh_hr")),
) -> dict:
    filename = (file.filename or "").lower()
    content = await file.read()

    if filename.endswith(".csv"):
        raw_records = _records_from_csv(content)
    elif filename.endswith(".xlsx"):
        raw_records = _records_from_xlsx(content)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chi ho tro .csv hoac .xlsx")

    if not raw_records:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rong hoac khong doc duoc du lieu")

    mapped = []
    for idx, record in enumerate(raw_records, start=2):
        mapped.append((idx, _map_import_record(record)))

    mssv_values = [str(payload.get("mssv", "")).strip() for _, payload in mapped if payload.get("mssv")]
    existing_by_mssv: dict[str, Member] = {}
    if mssv_values:
        existing_members = db.scalars(select(Member).where(Member.mssv.in_(mssv_values))).all()
        existing_by_mssv = {m.mssv: m for m in existing_members}

    results = {
        "total": len(mapped),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }

    for row_number, payload in mapped:
        mssv = str(payload.get("mssv", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not mssv or not name:
            results["failed"] += 1
            results["errors"].append({"row": row_number, "error": "Thieu mssv hoac name"})
            continue

        existing = existing_by_mssv.get(mssv)
        if existing and on_duplicate == "skip":
            results["skipped"] += 1
            continue

        try:
            body = MemberCreate(**payload)
        except ValidationError as exc:
            results["failed"] += 1
            results["errors"].append({"row": row_number, "error": exc.errors()})
            continue

        if existing:
            before = {
                "mssv": existing.mssv,
                "name": existing.name,
                "ban": existing.ban,
                "status": existing.status,
            }
            existing.name = body.name
            existing.gender = body.gender
            existing.dob = body.dob
            existing.ban = body.ban
            existing.role_title = body.roleTitle
            existing.status = body.status
            existing.phone = body.phone
            existing.email = str(body.email) if body.email else None
            existing.join_date = body.joinDate
            existing.lop = body.lop
            existing.chuyen_nganh = body.chuyenNganh
            existing.khoa = body.khoa
            existing.address = body.address
            existing.experience = body.experience
            existing.goal = body.goal
            existing.orientation = body.orientation
            results["updated"] += 1
            create_audit_log(
                db=db,
                action="IMPORT_UPDATE_MEMBER",
                resource_type="member",
                resource_id=existing.id,
                actor=current_user,
                before_snapshot=before,
                after_snapshot={"mssv": existing.mssv, "name": existing.name, "ban": existing.ban},
            )
        else:
            member = Member(
                mssv=body.mssv,
                name=body.name,
                gender=body.gender,
                dob=body.dob,
                ban=body.ban,
                role_title=body.roleTitle,
                status=body.status,
                phone=body.phone,
                email=str(body.email) if body.email else None,
                join_date=body.joinDate,
                lop=body.lop,
                chuyen_nganh=body.chuyenNganh,
                khoa=body.khoa,
                address=body.address,
                experience=body.experience,
                goal=body.goal,
                orientation=body.orientation,
            )
            db.add(member)
            db.flush()
            existing_by_mssv[member.mssv] = member
            results["created"] += 1
            create_audit_log(
                db=db,
                action="IMPORT_CREATE_MEMBER",
                resource_type="member",
                resource_id=member.id,
                actor=current_user,
                after_snapshot={"mssv": member.mssv, "name": member.name, "ban": member.ban},
            )

    db.commit()
    return api_response(data=results)


@router.get("")
def list_members(
    page: int = 1,
    page_size: int = Query(default=10, alias="pageSize"),
    q: str | None = None,
    ban: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str = "createdAt",
    order: str = "desc",
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("bcn", "bvh_hr", "bcm", "member", "bvh_finance", "bvh_discipline", "bvh_logistics")),
) -> dict:
    page, page_size = sanitize_pagination(page, page_size)
    stmt = select(Member)

    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Member.name).like(like) | func.lower(Member.mssv).like(like))
    if ban:
        stmt = stmt.where(Member.ban == ban)
    if status_filter:
        stmt = stmt.where(Member.status == status_filter)

    sort_columns = {
        "createdAt": Member.created_at,
        "name": Member.name,
        "mssv": Member.mssv,
        "ban": Member.ban,
        "status": Member.status,
    }
    sort_col = sort_columns.get(sort, Member.created_at)
    stmt = stmt.order_by(sort_col.asc() if order == "asc" else sort_col.desc())

    rows = db.scalars(stmt).all()
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    skills_map = _skills_by_member(db, [m.id for m in page_rows])

    # Attach current active/latest evaluation summary if possible
    cycle = db.scalar(
        select(EvaluationCycle)
        .where(EvaluationCycle.status.in_(["SCORING", "MEMBER_REVIEW", "READY_FOR_APPROVAL", "APPROVED", "LOCKED"]))
        .order_by(EvaluationCycle.start_date.desc())
    )
    eval_map = {}
    if cycle and page_rows:
        try:
            calc = EvaluationCalculatorService(db)
            for m in page_rows:
                try:
                    eval_map[m.id] = calc.compute_member_cycle(cycle.id, m.id)
                except EvaluationError:
                    eval_map[m.id] = None
        except Exception:
            eval_map = {}

    return api_response(
        data=[_member_out(m, eval_map.get(m.id), skills_map.get(m.id, [])) for m in page_rows],
        meta={"pagination": {"page": page, "pageSize": page_size, "total": total}},
    )


@router.get("/{member_id}")
def get_member(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn", "bvh_hr", "bcm", "member", "bvh_finance", "bvh_discipline", "bvh_logistics")),
) -> dict:
    if member_id == "me":
        member = db.scalar(select(Member).where(Member.mssv == current_user.username))
        if not member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay member")
        member_id = member.id
    else:
        member = db.get(Member, member_id)
        if not member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay member")

    skills = db.scalars(select(MemberSkill).where(MemberSkill.member_id == member_id)).all()
    return api_response(data=_member_out(member, skills=skills))


@router.get("/export")
def export_members(
    format: str = Query(default="csv"),
    ban: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("bcn", "bvh_hr")),
) -> StreamingResponse:
    if format not in {"csv", "zip"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Chi ho tro csv hoac zip"
        )

    stmt = select(Member)
    if ban:
        stmt = stmt.where(Member.ban == ban)
    if status_filter:
        stmt = stmt.where(Member.status == status_filter)

    members = db.scalars(stmt).all()

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "mssv", "name", "ban", "status", "phone", "email"])

        for m in members:
            writer.writerow([m.id, m.mssv, m.name, m.ban, m.status, m.phone, m.email])

        buffer.seek(0)
        headers = {"Content-Disposition": "attachment; filename=members.csv"}
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv", headers=headers
        )

    members_with_skills = []
    for m in members:
        skills = db.scalars(
            select(MemberSkill).where(MemberSkill.member_id == m.id)
        ).all()
        members_with_skills.append((m, list(skills)))

    buffer = generate_members_zip(members_with_skills)
    headers = {"Content-Disposition": "attachment; filename=members_profiles.zip"}
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers=headers,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_member(
    body: MemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn", "bvh_hr")),
) -> dict:
    exists = db.scalar(select(Member).where(Member.mssv == body.mssv))
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MSSV da ton tai")

    member = Member(
        mssv=body.mssv,
        name=body.name,
        gender=body.gender,
        dob=body.dob,
        ban=body.ban,
        role_title=body.roleTitle,
        status=body.status,
        phone=body.phone,
        email=str(body.email) if body.email else None,
        join_date=body.joinDate,
        lop=body.lop,
        chuyen_nganh=body.chuyenNganh,
        khoa=body.khoa,
        address=body.address,
        experience=body.experience,
        goal=body.goal,
        orientation=body.orientation,
    )
    db.add(member)
    db.flush()
    # persist skills if provided
    try:
        for s in getattr(body, "hardSkills", []) or []:
            db.add(MemberSkill(member_id=member.id, type="hard", name=s.name, level=s.level or ""))
        for s in getattr(body, "softSkills", []) or []:
            db.add(MemberSkill(member_id=member.id, type="soft", name=s.name, level=s.level or ""))
    except Exception:
        # ignore skill persistence errors here; commit will surface
        pass
    create_audit_log(
        db=db,
        action="CREATE_MEMBER",
        resource_type="member",
        resource_id=member.id,
        actor=current_user,
        after_snapshot={
            "mssv": member.mssv,
            "name": member.name,
            "ban": member.ban,
            "status": member.status,
        },
    )
    db.commit()
    db.refresh(member)
    skills = db.scalars(select(MemberSkill).where(MemberSkill.member_id == member.id)).all()
    return api_response(data=_member_out(member, skills=skills))


@router.patch("/{member_id}")
def update_member(
    member_id: str,
    body: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn", "bvh_hr")),
) -> dict:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay member"
        )

    payload = body.model_dump(exclude_none=True)
    before = {
        "mssv": member.mssv,
        "name": member.name,
        "gender": member.gender,
        "dob": member.dob,
        "ban": member.ban,
        "status": member.status,
        "role_title": member.role_title,
        "phone": member.phone,
        "email": member.email,
        "join_date": member.join_date,
        "lop": member.lop,
        "chuyen_nganh": member.chuyen_nganh,
        "khoa": member.khoa,
        "address": member.address,
        "experience": member.experience,
        "goal": member.goal,
        "orientation": member.orientation,
    }

    mapping = {
        "roleTitle": "role_title",
        "joinDate": "join_date",
        "chuyenNganh": "chuyen_nganh",
    }
    for key, value in payload.items():
        setattr(member, mapping.get(key, key), value)
    # handle skills replacement if provided
    if getattr(body, "hardSkills", None) is not None or getattr(body, "softSkills", None) is not None:
        existing_skills = db.scalars(select(MemberSkill).where(MemberSkill.member_id == member.id)).all()
        for es in existing_skills:
            db.delete(es)
        for s in getattr(body, "hardSkills", []) or []:
            db.add(MemberSkill(member_id=member.id, type="hard", name=s.name, level=s.level or ""))
        for s in getattr(body, "softSkills", []) or []:
            db.add(MemberSkill(member_id=member.id, type="soft", name=s.name, level=s.level or ""))
    create_audit_log(
        db=db,
        action="UPDATE_MEMBER",
        resource_type="member",
        resource_id=member.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "mssv": member.mssv,
            "name": member.name,
            "gender": member.gender,
            "dob": member.dob,
            "ban": member.ban,
            "status": member.status,
            "role_title": member.role_title,
            "phone": member.phone,
            "email": member.email,
            "join_date": member.join_date,
            "lop": member.lop,
            "chuyen_nganh": member.chuyen_nganh,
            "khoa": member.khoa,
            "address": member.address,
            "experience": member.experience,
            "goal": member.goal,
            "orientation": member.orientation,
        },
    )
    db.commit()
    db.refresh(member)
    skills = db.scalars(select(MemberSkill).where(MemberSkill.member_id == member.id)).all()
    return api_response(data=_member_out(member, skills=skills))


@router.patch("/{member_id}/status")
def update_member_status(
    member_id: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("bcn", "bvh_hr")),
) -> dict:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay member"
        )

    new_status = body.get("status")
    if new_status not in {"Active", "Inactive"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="status khong hop le"
        )

    member.status = new_status
    db.commit()
    db.refresh(member)
    skills = db.scalars(select(MemberSkill).where(MemberSkill.member_id == member.id)).all()
    return api_response(data=_member_out(member, skills=skills))


@router.get("/{member_id}/profile")
def export_member_profile(
    member_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "bcn",
            "bvh_hr",
            "bcm",
            "member",
            "bvh_finance",
            "bvh_discipline",
            "bvh_logistics",
        )
    ),
) -> StreamingResponse:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay member"
        )

    skills = db.scalars(select(MemberSkill).where(MemberSkill.member_id == member_id)).all()

    try:
        buffer = generate_member_profile_docx(member, skills)
        filename = f"HOSO_{member.mssv}_{member.name.replace(' ', '_')}.docx"
        headers = {"Content-Disposition": _attachment_content_disposition(filename)}
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi khi tao ho so: {str(e)}",
        )
