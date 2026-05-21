# HR Task 01-02: Chuẩn hóa xoá mềm thành viên và đồng bộ kỹ năng thành viên

## 1. Phạm vi tài liệu

Tài liệu này mô tả yêu cầu triển khai cho hai task thuộc module Quản lý nhân sự của MTEC Operations Hub:

- **Task 01:** Chuẩn hóa hành vi xoá thành viên giữa frontend và backend.
- **Task 02:** Lưu, cập nhật và trả về kỹ năng chuyên môn/kỹ năng mềm của thành viên thông qua bảng `member_skills`.

Các thay đổi liên quan đến hai repository:

- Frontend: `nmtrucworking/mtec-operations-hub`
- Backend: `nmtrucworking/mtec-operations-hub-backend`

## 2. Bối cảnh kỹ thuật hiện tại

### 2.1. Task 01

Frontend hiện có service gọi:

```ts
DELETE /api/v1/members/{member_id}
```

Tuy nhiên backend `app/routers/members.py` hiện đã có các nhóm endpoint sau:

- `GET /members`
- `GET /members/{member_id}`
- `POST /members`
- `PATCH /members/{member_id}`
- `PATCH /members/{member_id}/status`
- `GET /members/export`
- `GET /members/{member_id}/profile`
- `POST /members/import`
- `GET /members/import/template`

Chưa có endpoint `DELETE /members/{member_id}` tương ứng với frontend.

### 2.2. Task 02

Frontend đã gửi dữ liệu kỹ năng theo hai trường:

```ts
hardSkills: MemberSkill[]
softSkills: MemberSkill[]
```

Backend đã có model `MemberSkill` với các trường:

```py
member_id: str
type: str
name: str
level: str
```

Tuy nhiên schema `MemberCreate` và `MemberUpdate` chưa khai báo `hardSkills`/`softSkills`, và luồng create/update member chưa ghi dữ liệu vào bảng `member_skills`.

## 3. Nguyên tắc thiết kế

### 3.1. Không hard-delete dữ liệu nhân sự

Dữ liệu nhân sự là dữ liệu quản trị nội bộ, có liên quan đến lịch sử tham gia, kỷ luật, KPI, biên bản và audit log. Vì vậy, task 01 chọn hướng **xoá mềm**:

- Không xoá row khỏi bảng `members`.
- Chuyển `status` của thành viên sang `Inactive`.
- Ghi audit log với action `SOFT_DELETE_MEMBER`.
- Frontend có thể giữ nhãn hành động là “Xoá” nếu cần, nhưng thông báo phải thể hiện đây là thao tác ngừng hoạt động/lưu trữ hồ sơ.

### 3.2. Kỹ năng là dữ liệu con của hồ sơ thành viên

`MemberSkill` phải được xử lý như dữ liệu phụ thuộc của `Member`:

- Khi tạo member: tạo member trước, sau đó tạo danh sách kỹ năng.
- Khi cập nhật member: thay thế danh sách kỹ năng cũ bằng danh sách kỹ năng mới đã sanitize.
- Khi đọc member: trả về `hardSkills` và `softSkills` để frontend hiển thị đúng modal hồ sơ.
- Khi export DOCX/ZIP: truyền danh sách kỹ năng từ `member_skills` vào report service.

## 4. Task 01 — Chuẩn hóa xoá mềm thành viên

### 4.1. Mục tiêu

Tạo endpoint backend tương thích với frontend hiện tại:

```http
DELETE /api/v1/members/{member_id}
```

Endpoint này thực hiện xoá mềm bằng cách chuyển `Member.status = "Inactive"`.

### 4.2. Phân quyền

Chỉ các role sau được thực hiện:

- `bcn`
- `bvh_hr`

Các role khác chỉ được đọc dữ liệu theo quyền hiện có.

### 4.3. API contract

#### Request

```http
DELETE /api/v1/members/{member_id}
Authorization: Bearer <token>
```

#### Response thành công

```json
{
  "success": true,
  "data": {
    "id": "<member_id>",
    "status": "Inactive",
    "deleted": true,
    "mode": "soft"
  }
}
```

#### Error cases

| Trường hợp | HTTP status | Nội dung |
|---|---:|---|
| Không đăng nhập | 401 | Token thiếu hoặc không hợp lệ |
| Không đủ quyền | 403 | Role không thuộc `bcn`, `bvh_hr` |
| Không tìm thấy member | 404 | `Khong tim thay member` |
| Member đã inactive | 200 | Trả về id, status `Inactive`, `deleted: true` |

### 4.4. Backend implementation

Thêm vào `app/routers/members.py`:

```py
@router.delete("/{member_id}")
def delete_member(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn", "bvh_hr")),
) -> dict:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Khong tim thay member",
        )

    before = {
        "mssv": member.mssv,
        "name": member.name,
        "status": member.status,
    }

    member.status = "Inactive"

    create_audit_log(
        db=db,
        action="SOFT_DELETE_MEMBER",
        resource_type="member",
        resource_id=member.id,
        actor=current_user,
        before_snapshot=before,
        after_snapshot={
            "mssv": member.mssv,
            "name": member.name,
            "status": member.status,
            "delete_mode": "soft",
        },
    )

    db.commit()
    db.refresh(member)
    return api_response(
        data={
            "id": member.id,
            "status": member.status,
            "deleted": True,
            "mode": "soft",
        }
    )
```

### 4.5. Frontend update

File liên quan:

```text
src/services/members.ts
src/views/MembersView.tsx
```

Yêu cầu:

1. Có thể giữ hàm `deleteMember()` vì backend đã tương thích endpoint `DELETE`.
2. Sửa text xác nhận từ:

```text
Bạn có chắc chắn muốn xóa thành viên này?
```

thành:

```text
Bạn có chắc chắn muốn chuyển thành viên này sang trạng thái Ngừng hoạt động? Hồ sơ vẫn được lưu trữ trong hệ thống.
```

3. Sau khi thao tác thành công, hiển thị toast:

```text
Đã chuyển thành viên sang trạng thái Ngừng hoạt động.
```

4. Không xoá record khỏi bảng hiển thị nếu bộ lọc trạng thái đang là `All`; nếu đang lọc `Active`, record sẽ biến mất sau refresh do backend trả status `Inactive`.

### 4.6. Acceptance criteria

- `DELETE /api/v1/members/{id}` hoạt động với `bcn` và `bvh_hr`.
- Role `member`, `bcm`, `bvh_finance`, `bvh_discipline`, `bvh_logistics` nhận 403 khi gọi endpoint.
- Record trong bảng `members` không bị xoá vật lý.
- `status` chuyển sang `Inactive`.
- Audit log ghi action `SOFT_DELETE_MEMBER`.
- Frontend không còn lỗi khi nhấn nút xoá thành viên.

## 5. Task 02 — Đồng bộ kỹ năng thành viên vào `member_skills`

### 5.1. Mục tiêu

Đảm bảo hồ sơ thành viên lưu đúng hai nhóm kỹ năng:

- `hardSkills`: kỹ năng chuyên môn
- `softSkills`: kỹ năng mềm

Mỗi kỹ năng có cấu trúc:

```ts
{
  name: string;
  level: "Cơ bản" | "Trung bình" | "Tốt";
}
```

### 5.2. Schema backend

Cập nhật `app/schemas.py`:

```py
class MemberSkillIn(BaseModel):
    name: str
    level: str


class MemberCreate(BaseModel):
    ...
    hardSkills: list[MemberSkillIn] = Field(default_factory=list)
    softSkills: list[MemberSkillIn] = Field(default_factory=list)


class MemberUpdate(BaseModel):
    ...
    hardSkills: list[MemberSkillIn] | None = None
    softSkills: list[MemberSkillIn] | None = None
```

### 5.3. Validation

Backend phải sanitize dữ liệu kỹ năng trước khi lưu:

| Điều kiện | Hành vi |
|---|---|
| `name` rỗng sau khi trim | Bỏ qua skill |
| `level` không thuộc `Cơ bản`, `Trung bình`, `Tốt` | Chuẩn hóa về `Cơ bản` hoặc trả 422 tùy chính sách |
| Skill trùng tên trong cùng nhóm | Giữ một bản ghi sau normalize |
| `hardSkills`/`softSkills` không gửi lên | Không thay đổi trong update |
| `hardSkills`/`softSkills` gửi mảng rỗng | Xoá toàn bộ skill thuộc nhóm tương ứng |

Khuyến nghị cho MVP: normalize level không hợp lệ về `Cơ bản` để tránh làm hỏng flow import/form.

### 5.4. Backend helper functions

Thêm helper vào `app/routers/members.py`:

```py
VALID_SKILL_LEVELS = {"Cơ bản", "Trung bình", "Tốt"}


def _normalize_skill_level(level: str | None) -> str:
    if level in VALID_SKILL_LEVELS:
        return level
    text = (level or "").strip().lower()
    if "tốt" in text or "good" in text:
        return "Tốt"
    if "trung" in text or "medium" in text:
        return "Trung bình"
    return "Cơ bản"


def _sanitize_skills(skills: list | None) -> list[dict]:
    if not skills:
        return []

    result = []
    seen = set()
    for item in skills:
        name = (getattr(item, "name", None) or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "name": name,
            "level": _normalize_skill_level(getattr(item, "level", None)),
        })
    return result


def _replace_member_skills(
    db: Session,
    member_id: str,
    *,
    hard_skills: list | None = None,
    soft_skills: list | None = None,
) -> None:
    if hard_skills is not None:
        old_hard = db.scalars(
            select(MemberSkill).where(
                MemberSkill.member_id == member_id,
                MemberSkill.type == "hard",
            )
        ).all()
        for row in old_hard:
            db.delete(row)
        for skill in _sanitize_skills(hard_skills):
            db.add(MemberSkill(
                member_id=member_id,
                type="hard",
                name=skill["name"],
                level=skill["level"],
            ))

    if soft_skills is not None:
        old_soft = db.scalars(
            select(MemberSkill).where(
                MemberSkill.member_id == member_id,
                MemberSkill.type == "soft",
            )
        ).all()
        for row in old_soft:
            db.delete(row)
        for skill in _sanitize_skills(soft_skills):
            db.add(MemberSkill(
                member_id=member_id,
                type="soft",
                name=skill["name"],
                level=skill["level"],
            ))
```

### 5.5. Output format

Cập nhật `_member_out()` để trả về kỹ năng:

```py
def _skills_out(skills: list[MemberSkill], skill_type: str) -> list[dict]:
    return [
        {"name": skill.name, "level": skill.level}
        for skill in skills
        if skill.type == skill_type
    ]
```

Khuyến nghị sửa `_member_out()` nhận thêm `skills`:

```py
def _member_out(member: Member, disc: DisciplineRecord | None = None, skills: list[MemberSkill] | None = None) -> dict:
    skills = skills or []
    return {
        ...,
        "hardSkills": _skills_out(skills, "hard"),
        "softSkills": _skills_out(skills, "soft"),
    }
```

### 5.6. Create member flow

Sau `db.flush()` trong `create_member()`:

```py
_replace_member_skills(
    db,
    member.id,
    hard_skills=body.hardSkills,
    soft_skills=body.softSkills,
)
```

Sau đó commit như hiện tại.

### 5.7. Update member flow

Trong `update_member()`:

1. Tách `hardSkills` và `softSkills` khỏi payload trước khi `setattr`.
2. Chỉ thay nhóm skill nếu field đó xuất hiện trong request.

Ví dụ:

```py
payload = body.model_dump(exclude_unset=True)
hard_skills = payload.pop("hardSkills", None)
soft_skills = payload.pop("softSkills", None)

for key, value in payload.items():
    setattr(member, mapping.get(key, key), value)

_replace_member_skills(
    db,
    member.id,
    hard_skills=hard_skills if "hardSkills" in body.model_fields_set else None,
    soft_skills=soft_skills if "softSkills" in body.model_fields_set else None,
)
```

### 5.8. List/detail member flow

Hiện tại list member trả member trực tiếp từ bảng `members`. Cần bổ sung lấy skill theo `member_id`.

MVP implementation:

```py
member_ids = [member.id for member in members]
skill_rows = db.scalars(select(MemberSkill).where(MemberSkill.member_id.in_(member_ids))).all()
skills_by_member = {}
for skill in skill_rows:
    skills_by_member.setdefault(skill.member_id, []).append(skill)

return api_response(
    data=[_member_out(member, skills=skills_by_member.get(member.id, [])) for member in members],
    meta={"page": page, "pageSize": pageSize, "total": total},
)
```

Detail endpoint:

```py
skills = db.scalars(select(MemberSkill).where(MemberSkill.member_id == member_id)).all()
return api_response(data=_member_out(member, disc=disc, skills=skills))
```

### 5.9. Import flow

CSV/XLSX import hiện chưa có cấu trúc chuẩn cho nhiều kỹ năng. Có hai hướng:

#### Phase 1 — Không bắt buộc import skill

Giữ import hiện tại chỉ nhập thông tin hồ sơ cơ bản. Skill được thêm/sửa qua form chi tiết.

#### Phase 2 — Import skill bằng cột text

Bổ sung các cột:

```csv
hardSkills,softSkills
"Lập trình:Cơ bản; Website:Tốt","Giao tiếp:Trung bình; Làm việc nhóm:Tốt"
```

Parser:

```py
def _parse_skill_text(value: str | None) -> list[dict]:
    if not value:
        return []
    result = []
    for chunk in value.split(";"):
        name, _, level = chunk.partition(":")
        name = name.strip()
        if not name:
            continue
        result.append({"name": name, "level": _normalize_skill_level(level.strip())})
    return result
```

Khuyến nghị triển khai Phase 1 trước để giảm rủi ro sai định dạng dữ liệu.

### 5.10. Frontend update

File liên quan:

```text
src/data/members.ts
src/services/members.ts
src/views/MembersView.tsx
```

Yêu cầu:

- Giữ payload `hardSkills` và `softSkills` như hiện tại.
- Đảm bảo `normalizeMember()` đọc được `hardSkills` và `softSkills` từ response backend.
- Không cần thay đổi lớn ở form nếu backend đã nhận và trả dữ liệu đúng contract.

### 5.11. Acceptance criteria

- Khi tạo member với `hardSkills`/`softSkills`, backend ghi dữ liệu vào `member_skills`.
- Khi cập nhật member, danh sách skill được thay thế đúng theo payload mới.
- Khi đọc danh sách member, mỗi member có `hardSkills` và `softSkills`.
- Khi đọc chi tiết member, modal frontend hiển thị lại đúng kỹ năng đã lưu.
- Skill rỗng không được lưu.
- Skill trùng tên trong cùng nhóm không tạo bản ghi trùng.
- Export hồ sơ DOCX có thể nhận danh sách kỹ năng từ `member_skills`.

## 6. Test cases bắt buộc

### 6.1. Backend test cases

| Test | Mục tiêu |
|---|---|
| `test_delete_member_soft_delete_success` | `bvh_hr` gọi DELETE, status chuyển `Inactive` |
| `test_delete_member_forbidden_for_member_role` | role `member` nhận 403 |
| `test_delete_member_not_found` | id không tồn tại nhận 404 |
| `test_create_member_with_skills` | create member lưu skill vào `member_skills` |
| `test_update_member_replace_skills` | update thay thế danh sách skill cũ |
| `test_list_members_returns_skills` | list trả `hardSkills`/`softSkills` |
| `test_get_member_returns_skills` | detail trả đủ kỹ năng |
| `test_empty_skill_name_is_ignored` | skill name rỗng không được lưu |

### 6.2. Frontend test/manual checklist

- Đăng nhập bằng `bvh_hr`.
- Tạo thành viên có ít nhất 1 hard skill và 1 soft skill.
- Refresh trang, mở lại hồ sơ, kiểm tra skill vẫn còn.
- Sửa skill, refresh, kiểm tra skill mới thay thế skill cũ.
- Nhấn xoá thành viên, xác nhận thông báo xoá mềm.
- Lọc `Active`, xác nhận thành viên đã chuyển khỏi danh sách active.
- Lọc `Inactive`, xác nhận hồ sơ vẫn tồn tại.

## 7. Definition of Done

Task 01 được xem là hoàn tất khi:

- Backend có endpoint `DELETE /api/v1/members/{member_id}`.
- Endpoint thực hiện soft-delete, không hard-delete.
- Frontend thao tác xoá không còn lỗi API.
- Audit log ghi nhận được thao tác.

Task 02 được xem là hoàn tất khi:

- Backend schema nhận `hardSkills` và `softSkills`.
- `member_skills` được ghi khi tạo/cập nhật member.
- List/detail member trả đủ skill cho frontend.
- Frontend không cần mock skill sau khi refresh.
- Có test hoặc checklist xác nhận dữ liệu còn tồn tại sau reload.

## 8. Thứ tự triển khai khuyến nghị

1. Backend Task 01: thêm soft-delete endpoint.
2. Frontend Task 01: sửa wording xác nhận/toast.
3. Backend Task 02: cập nhật schema và helper skill.
4. Backend Task 02: cập nhật create/update/list/detail/export.
5. Frontend Task 02: kiểm tra normalize response và hiển thị modal.
6. Test regression cho MembersView và DisciplineView.

## 9. Rủi ro kỹ thuật

| Rủi ro | Ảnh hưởng | Biện pháp |
|---|---|---|
| Hard-delete làm mất liên kết kỷ luật/điểm danh/evaluation | Cao | Chỉ dùng soft-delete |
| Frontend gửi skill nhưng backend bỏ qua | Cao | Cập nhật schema và tests |
| N+1 query khi list member kèm skill | Trung bình | Batch query `MemberSkill` theo danh sách member id |
| Skill import sai định dạng | Trung bình | Để import skill sang Phase 2 |
| Lệch ngôn ngữ level kỹ năng | Thấp - Trung bình | Normalize `good/medium/basic` và tiếng Việt về 3 mức chuẩn |
