# BE Implementation Guide: Export Member Profile & Member Evaluation Sheet

## 1. Mục tiêu

Tài liệu này mô tả cách backend triển khai tách biệt 2 service export DOCX trong hệ thống MTEC Operations Hub:

1. `member_profile_export_service.py`  
   Export **hồ sơ thành viên** từ dữ liệu `Member` và `MemberSkill`.

2. `member_evaluation_export_service.py`  
   Export **phiếu đánh giá thành viên** từ dữ liệu báo cáo đánh giá của một thành viên trong một chu kỳ đánh giá.

Mục tiêu chính là tránh gộp sai trách nhiệm vào `report_service.py`. `report_service.py` chỉ nên giữ vai trò tương thích ngược nếu còn import cũ, không nên chứa implementation export chính.

---

## 2. Nguyên tắc thiết kế

### 2.1. Single Responsibility Principle

Mỗi service chỉ xử lý một nhóm nghiệp vụ export:

| Service | Trách nhiệm | Không nên làm |
|---|---|---|
| `member_profile_export_service.py` | Tạo DOCX hồ sơ thành viên | Không xử lý dữ liệu đánh giá/KPI |
| `member_evaluation_export_service.py` | Tạo DOCX phiếu đánh giá thành viên | Không xử lý hồ sơ thành viên cơ bản |
| `evaluation_export.py` | Điều phối export báo cáo đánh giá CSV/XLSX/DOCX | Không chứa logic dựng DOCX phiếu đánh giá chi tiết |
| `report_service.py` | Compatibility layer, nếu cần | Không chứa implementation chính |

### 2.2. Template-first, fallback-safe

Cả 2 service nên ưu tiên render bằng template DOCX/DOTX nếu file template tồn tại.  
Riêng phiếu đánh giá nên có fallback DOCX tự dựng bằng `python-docx` để endpoint không bị chết khi chưa có template.

### 2.3. Không đổi endpoint nếu chưa cần

Giữ endpoint hiện có để không phá frontend/API client:

```http
GET /members/{member_id}/profile
GET /evaluations/reports/cycles/{cycle_id}/members/{member_id}/exports/report.docx
```

---

## 3. Cấu trúc file cần có

```text
app/
  services/
    member_profile_export_service.py
    member_evaluation_export_service.py
    evaluation_export.py
    report_service.py
  routers/
    members.py
    v2/
      evaluation_reports.py
  assets/
    templates/
      member_profile_template.docx
      member_evaluation_sheet_template.docx        # optional
      member_evaluation_sheet_template.dotx        # optional
      BM-MTEC-NS-03 - Phiếu đánh giá thành viên.dotx # optional
```

---

## 4. Service 1: Export hồ sơ thành viên

### 4.1. File

```text
app/services/member_profile_export_service.py
```

### 4.2. Public functions

```python
def format_date(d: date | None) -> str: ...

def generate_member_profile_docx(
    member: Member,
    skills: list[MemberSkill],
) -> BytesIO: ...

def generate_members_zip(
    members_with_skills: list[tuple[Member, list[MemberSkill]]],
) -> BytesIO: ...
```

### 4.3. Dữ liệu đầu vào

| Tham số | Kiểu | Nguồn |
|---|---|---|
| `member` | `Member` | DB query theo `member_id` |
| `skills` | `list[MemberSkill]` | DB query theo `member_id` |

### 4.4. Template path

```python
TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "assets",
    "templates",
)

MEMBER_PROFILE_TEMPLATE_PATH = os.path.join(
    TEMPLATE_DIR,
    "member_profile_template.docx",
)
```

### 4.5. Context cần render cho hồ sơ thành viên

| Field template | Dữ liệu |
|---|---|
| `ho_ten` | `member.name.upper()` |
| `gioi_tinh` | `member.gender` |
| `ngay_sinh` | `member.dob` format `dd/mm/yyyy` |
| `mssv` | `member.mssv` |
| `khoa` | `member.khoa` |
| `chuyen_nganh` | `member.chuyen_nganh` |
| `sdt` | `member.phone` |
| `email` | `member.email` |
| `muc_tieu` | `member.goal` |
| `dinh_huong` | `member.orientation` |
| `vi_tri` | `member.role_title` |
| `c_ban_cn` | Checkbox Ban Công nghệ |
| `c_ban_tt` | Checkbox Ban Truyền thông |
| `c_ban_vh` | Checkbox Ban Vận hành |
| `c_ban_cnh` | Checkbox Ban Chủ nhiệm |
| `c_ban_khac` | Checkbox khác |

### 4.6. Skill mapping

Service hồ sơ thành viên cần map kỹ năng theo keyword:

```python
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
```

Mỗi kỹ năng cần có checkbox:

```text
{key}
{key}_cb
{key}_tb
{key}_tot
```

Trong đó:

| Suffix | Ý nghĩa |
|---|---|
| `_cb` | Cơ bản |
| `_tb` | Trung bình |
| `_tot` | Tốt |

---

## 5. Service 2: Export phiếu đánh giá thành viên

### 5.1. File

```text
app/services/member_evaluation_export_service.py
```

### 5.2. Public function

```python
def generate_member_evaluation_sheet_docx(
    report: dict[str, Any],
    actor: User | None = None,
) -> BytesIO: ...
```

### 5.3. Dữ liệu đầu vào

`report` phải lấy từ:

```python
EvaluationReportService(db).get_member_report(cycle_id, member_id)
```

`actor` là user đang thực hiện export, lấy từ `get_current_user`.

### 5.4. Template path

```python
TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "assets",
    "templates",
)

MEMBER_EVALUATION_TEMPLATE_PATHS = [
    os.path.join(TEMPLATE_DIR, "member_evaluation_sheet_template.docx"),
    os.path.join(TEMPLATE_DIR, "member_evaluation_sheet_template.dotx"),
    os.path.join(TEMPLATE_DIR, "BM-MTEC-NS-03 - Phiếu đánh giá thành viên.dotx"),
]
```

Service cần tìm template theo thứ tự trên. Nếu không có template, tạo fallback DOCX bằng `python-docx`.

### 5.5. Report shape tối thiểu

```python
{
    "cycleId": str,
    "cycleCode": str,
    "cycleName": str,
    "status": str,
    "reportVersion": str,
    "generatedAt": datetime | str | None,
    "member": {
        "id": str,
        "mssv": str,
        "name": str,
        "ban": str,
        "unitCode": str,
        "roleTitle": str,
        "status": str,
    },
    "scores": {
        "componentI": float,
        "componentII": float,
        "componentIIIa": float,
        "componentIIIb": float,
        "total": float,
        "attendanceRate": float,
    },
    "classification": {
        "preliminary": str,
        "final": str,
    },
    "blockers": list[dict],
    "breakdowns": list[dict],
    "evidence": list[dict],
    "appeals": list[dict],
    "disciplineCases": list[dict],
}
```

### 5.6. Classification labels

```python
CLASSIFICATION_LABELS = {
    "EXCELLENT": "Xuất sắc",
    "GOOD": "Tốt",
    "PASSED": "Đạt",
    "NEEDS_IMPROVEMENT": "Cần cải thiện",
    "FAILED": "Không đạt",
}
```

### 5.7. Context cần render cho phiếu đánh giá

#### 5.7.1. Thông tin chu kỳ

| Context key | Nguồn |
|---|---|
| `cycle_id` | `report.cycleId` |
| `cycle_code` | `report.cycleCode` |
| `cycle_name` | `report.cycleName` |
| `cycle_status` | `report.status` |
| `report_version` | `report.reportVersion` |
| `generated_at` | thời điểm export |
| `generated_day` | ngày export |
| `generated_month` | tháng export |
| `generated_year` | năm export |
| `exported_by` | `actor.full_name` hoặc `actor.username` |
| `exported_by_username` | `actor.username` |

#### 5.7.2. Thông tin thành viên

| Context key | Nguồn |
|---|---|
| `member_id` | `member.id` |
| `mssv` | `member.mssv` |
| `ho_ten` | `member.name` |
| `ban` | `member.ban` |
| `unit_code` | `member.unitCode` |
| `role_title` | `member.roleTitle` |
| `member_status` | `member.status` |

#### 5.7.3. Điểm đánh giá

| Context key | Nguồn |
|---|---|
| `component_i_score` | `scores.componentI` |
| `component_ii_score` | `scores.componentII` |
| `component_iii_a_score` | `scores.componentIIIa` |
| `component_iii_b_score` | `scores.componentIIIb` |
| `total_score` | `scores.total` |
| `attendance_rate` | `scores.attendanceRate` |
| `preliminary_classification` | `classification.preliminary` |
| `preliminary_classification_label` | label tiếng Việt |
| `final_classification` | `classification.final` |
| `final_classification_label` | label tiếng Việt |
| `blockers_text` | text tổng hợp blockers |

#### 5.7.4. Checkbox xếp loại

| Context key | Điều kiện checked |
|---|---|
| `c_xuat_sac` | `final_classification == "EXCELLENT"` |
| `c_tot` | `final_classification == "GOOD"` |
| `c_dat` | `final_classification == "PASSED"` |
| `c_can_cai_thien` | `final_classification == "NEEDS_IMPROVEMENT"` |
| `c_khong_dat` | `final_classification == "FAILED"` |

### 5.8. Row context cho bảng điểm chi tiết

Mỗi item trong `breakdown_rows`:

```python
{
    "criterion_code": str,
    "component": str,
    "unit_code": str,
    "raw_score": str,
    "final_score": str,
    "max_score": str,
    "evidence_count": str,
    "calculation_note": str,
}
```

Nguồn từ `report["breakdowns"]`:

| Row key | Nguồn |
|---|---|
| `criterion_code` | `criterionCode` |
| `component` | `component` |
| `unit_code` | `unitCode` |
| `raw_score` | `rawScore` |
| `final_score` | `finalScore` |
| `max_score` | `maxScoreSnapshot` |
| `evidence_count` | `evidenceCount` |
| `calculation_note` | `calculationNote` |

### 5.9. Row context cho minh chứng

Mỗi item trong `evidence_rows`:

```python
{
    "title": str,
    "type": str,
    "status": str,
    "url": str,
    "description": str,
    "captured_at": str,
}
```

### 5.10. Row context cho phúc khảo/khiếu nại

Mỗi item trong `appeal_rows`:

```python
{
    "criterion_code": str,
    "appeal_type": str,
    "status": str,
    "requested_score": str,
    "content": str,
    "resolution_note": str,
}
```

### 5.11. Row context cho hồ sơ kỷ luật liên quan

Mỗi item trong `discipline_case_rows`:

```python
{
    "case_code": str,
    "case_type": str,
    "severity": str,
    "status": str,
    "title": str,
    "blocker_code": str,
    "point_impact": str,
}
```

---

## 6. Tích hợp với EvaluationExportService

File:

```text
app/services/evaluation_export.py
```

Import trực tiếp service phiếu đánh giá:

```python
from app.services.member_evaluation_export_service import generate_member_evaluation_sheet_docx
```

Sửa hàm export DOCX của một thành viên:

```python
def export_member_report_docx(
    self,
    cycle_id: str,
    member_id: str,
    *,
    actor: User,
) -> bytes:
    report = self.report_service.get_member_report(cycle_id, member_id)
    stream = generate_member_evaluation_sheet_docx(report, actor=actor)
    return stream.getvalue()
```

Không để `EvaluationExportService` tự dựng bảng DOCX chi tiết bằng `python-docx` nữa. Service này chỉ điều phối lấy report và gọi service export chuyên trách.

---

## 7. Tích hợp với members router

File:

```text
app/routers/members.py
```

Import trực tiếp service hồ sơ thành viên:

```python
from app.services.member_profile_export_service import (
    generate_member_profile_docx,
    generate_members_zip,
)
```

Endpoint hiện có giữ nguyên:

```http
GET /members/{member_id}/profile
```

Luồng xử lý:

```text
member_id
  -> get Member
  -> get MemberSkill list
  -> generate_member_profile_docx(member, skills)
  -> StreamingResponse DOCX
```

---

## 8. Tích hợp với evaluation_reports router

File:

```text
app/routers/v2/evaluation_reports.py
```

Endpoint giữ nguyên:

```http
GET /evaluations/reports/cycles/{cycle_id}/members/{member_id}/exports/report.docx
```

Luồng xử lý:

```text
cycle_id + member_id
  -> _ensure_member_report_access(...)
  -> EvaluationExportService(db).export_member_report_docx(cycle_id, member_id, actor=current_user)
  -> create_audit_log(...)
  -> Response DOCX
```

Audit action nên giữ:

```python
EXPORT_MEMBER_EVALUATION_REPORT
```

Response media type:

```text
application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

---

## 9. Vai trò của report_service.py

`report_service.py` chỉ nên giữ wrapper tương thích nếu code cũ còn import:

```python
"""Backward-compatible exports for legacy imports."""

from app.services.member_evaluation_export_service import generate_member_evaluation_sheet_docx
from app.services.member_profile_export_service import (
    format_date,
    generate_member_profile_docx,
    generate_members_zip,
)

__all__ = [
    "format_date",
    "generate_member_profile_docx",
    "generate_members_zip",
    "generate_member_evaluation_sheet_docx",
]
```

Không thêm logic mới vào file này.

---

## 10. Helper functions khuyến nghị cho service phiếu đánh giá

### 10.1. Format datetime

```python
def _format_datetime(value: datetime | None = None) -> str:
    value = value or datetime.now(UTC)
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.strftime("%d/%m/%Y %H:%M")
```

### 10.2. Format number

```python
def _format_number(value: Any) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")
```

### 10.3. Format percent

```python
def _format_percent(value: Any) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if 0 <= number <= 1:
        number *= 100
    return f"{number:.2f}%".replace(".00%", "%")
```

### 10.4. Blockers text

```python
def _blockers_text(blockers: list[Any]) -> str:
    if not blockers:
        return "Không ghi nhận"
    ...
```

Yêu cầu: nếu blocker có `code`, `cap`, `source`, `title` thì nối thành text dễ đọc trong phiếu đánh giá.

---

## 11. Fallback DOCX cho phiếu đánh giá

Nếu chưa có template BM-MTEC-NS-03, service phiếu đánh giá phải tự tạo DOCX với các phần sau:

1. Tiêu đề: `PHIẾU ĐÁNH GIÁ THÀNH VIÊN`
2. Thông tin chu kỳ
3. Thông tin thành viên
4. Kết quả tổng hợp
5. Yếu tố giới hạn/xử lý đặc biệt
6. Bảng điểm chi tiết
7. Minh chứng, nếu có
8. Phúc khảo/khiếu nại, nếu có
9. Hồ sơ kỷ luật liên quan, nếu có
10. Khu vực xác nhận Ban Vận hành

Fallback này giúp API vẫn export được trong giai đoạn chưa có template chính thức.

---

## 12. Test checklist

### 12.1. Unit test service hồ sơ thành viên

Cần kiểm tra:

- Có template `member_profile_template.docx` thì tạo được `BytesIO`.
- Thiếu template thì raise `FileNotFoundError`.
- Ban được check đúng checkbox.
- Skill level được map đúng `_cb`, `_tb`, `_tot`.

### 12.2. Unit test service phiếu đánh giá

Cần kiểm tra:

- Không có template vẫn tạo được fallback DOCX.
- `total_score`, `attendance_rate`, `final_classification_label` được format đúng.
- `breakdown_rows` được tạo đúng số dòng.
- `evidence_rows`, `appeal_rows`, `discipline_case_rows` không làm service lỗi khi list rỗng.
- Actor rỗng không làm service lỗi.

### 12.3. Integration test endpoint hồ sơ thành viên

```http
GET /members/{member_id}/profile
```

Kỳ vọng:

- Status `200`.
- Header `Content-Type` là DOCX.
- Header `Content-Disposition` có filename UTF-8 an toàn.
- Body không rỗng.

### 12.4. Integration test endpoint phiếu đánh giá

```http
GET /evaluations/reports/cycles/{cycle_id}/members/{member_id}/exports/report.docx
```

Kỳ vọng:

- User có quyền thì status `200`.
- User không có quyền thì status `403`.
- Cycle/member không tồn tại thì status `404`.
- Header `Content-Type` là DOCX.
- Body không rỗng.
- Có audit log `EXPORT_MEMBER_EVALUATION_REPORT`.

---

## 13. Acceptance criteria

BE được xem là triển khai đạt khi:

- [ ] Có file `app/services/member_profile_export_service.py`.
- [ ] Có file `app/services/member_evaluation_export_service.py`.
- [ ] `members.py` import trực tiếp từ `member_profile_export_service.py`.
- [ ] `evaluation_export.py` import trực tiếp từ `member_evaluation_export_service.py`.
- [ ] `report_service.py` không chứa implementation export chính, chỉ giữ compatibility nếu cần.
- [ ] Endpoint export hồ sơ thành viên vẫn hoạt động.
- [ ] Endpoint export phiếu đánh giá thành viên vẫn hoạt động.
- [ ] Có fallback DOCX cho phiếu đánh giá khi thiếu template.
- [ ] Có audit log cho export phiếu đánh giá.
- [ ] Test không lỗi import vòng hoặc lỗi thiếu dependency.

---

## 14. Lệnh kiểm tra local

```bash
pytest
uvicorn app.main:app --reload
```

Kiểm tra thủ công bằng API client:

```http
GET /members/{member_id}/profile
GET /evaluations/reports/cycles/{cycle_id}/members/{member_id}/exports/report.docx
```

---

## 15. Ghi chú triển khai

- Không commit template binary bằng markdown hướng dẫn này. Template `.docx`/`.dotx` cần được thêm riêng nếu đã chốt biểu mẫu.
- Nếu template BM-MTEC-NS-03 có tên biến khác context trong tài liệu này, ưu tiên cập nhật service context hoặc cập nhật template để thống nhất.
- Nếu frontend cần tên endpoint riêng cho `phiếu đánh giá`, có thể bổ sung alias endpoint sau, nhưng không nên xóa endpoint hiện tại để tránh breaking change.
