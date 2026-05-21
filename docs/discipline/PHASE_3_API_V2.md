# Phase 3 Implementation Guide - Evaluation API v2

## 1. Mục tiêu Phase 3

Phase 3 xây dựng lớp API cho module `evaluations` trên `/api/v2`. Mục tiêu là expose các service đã thiết kế ở Phase 2 thành các endpoint có phân quyền, request/response schema rõ ràng, error mapping ổn định và không làm thay đổi hành vi của API v1 legacy.

Phase này không viết lại công thức tính điểm trong router. Router chỉ thực hiện xác thực, phân quyền, validate request, gọi service và trả response chuẩn.

## 2. Đầu vào của Phase 3

Phase 3 giả định các phần sau đã có hoặc sẽ được triển khai song song theo tài liệu Phase 1 và Phase 2:

- Core schema/migration cho `evaluations`.
- `EvaluationCalculatorService`.
- `ClassificationPolicyService`.
- `EvidenceValidationService`.
- `EvaluationCriteriaSeedService`.
- `EvaluationSyncService`.
- Constants và error classes cho evaluation domain.

## 3. Phạm vi thực hiện

### 3.1. Trong phạm vi

| Hạng mục | Mục tiêu |
|---|---|
| API router | Tạo router `/api/v2/evaluations`. |
| Request/response schemas | Tạo Pydantic schemas cho cycle, criteria, score event, evidence, member role, compute result. |
| RBAC | Áp quyền theo role hiện có và chuẩn bị unit-level permission. |
| Error mapping | Map domain errors thành HTTP status và response chuẩn. |
| Integration tests | Kiểm tra endpoint, role, status code, response shape. |
| API docs | Đảm bảo Swagger/OpenAPI có request/response rõ. |

### 3.2. Ngoài phạm vi

| Hạng mục | Lý do |
|---|---|
| UI/frontend | Không thuộc backend API phase. |
| Workflow đối soát đầy đủ | Phase 3 chỉ tạo endpoint khung; luồng nghiệp vụ chi tiết thuộc Phase 4. |
| Import dữ liệu legacy | Thuộc Phase 5. |
| Export báo cáo | Sau khi API và workflow ổn định. |
| Refactor toàn bộ v1 Discipline | Giữ legacy để tránh phá hệ thống hiện tại. |

## 4. File cần tạo hoặc chỉnh sửa

```text
app/routers/v2/evaluations.py
app/routers/v2/__init__.py
app/schemas.py
app/core/evaluation_errors.py
app/core/evaluation_constants.py
app/services/evaluation_calculator.py
app/services/evaluation_criteria_seed.py
app/services/evaluation_evidence.py
app/services/evaluation_sync.py
tests/test_evaluation_api_v2.py
docs/discipline/PHASE_3_API_V2.md
```

Ghi chú:

- Nếu Phase 2 đã tạo `evaluation_errors.py`, không tạo lại.
- Nếu muốn tránh `app/schemas.py` quá lớn, có thể tạo `app/schemas_evaluation.py`, nhưng cần thống nhất import style với repo hiện tại.
- `app/routers/v2/__init__.py` hiện mới mount auth, cần mount thêm `evaluations_router`.

## 5. Nguyên tắc API

1. API v2 không phá API v1.
2. Endpoint mutating phải kiểm tra role.
3. Member chỉ được xem dữ liệu của chính mình, trừ khi có role quản trị.
4. Không cho sửa trực tiếp kỳ đã `LOCKED`.
5. Không cho compute nếu thiếu tiêu chí bắt buộc.
6. Không cho ghi score event thiếu minh chứng khi endpoint chạy ở mode chính thức.
7. Response dùng wrapper chuẩn `api_response` nếu repo đang dùng convention này.
8. Không trả raw SQLAlchemy model.
9. Không để router chứa logic tính điểm hoặc xếp loại.
10. Domain errors phải được map sang error response nhất quán.

## 6. Router mount

File:

```text
app/routers/v2/__init__.py
```

Cần bổ sung:

```python
from .evaluations import router as evaluations_router

api_v2_router.include_router(evaluations_router)
```

Router chính:

```python
router = APIRouter(prefix="/evaluations", tags=["evaluations"])
```

Base path sau khi mount:

```text
/api/v2/evaluations
```

## 7. Endpoint matrix

## 7.1. Evaluation cycles

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `POST` | `/cycles` | `bcn`, `bvh_discipline`, `bvh_hr` | Tạo kỳ đánh giá. |
| `GET` | `/cycles` | authenticated | Danh sách kỳ đánh giá. |
| `GET` | `/cycles/{cycle_id}` | authenticated | Chi tiết kỳ đánh giá. |
| `PATCH` | `/cycles/{cycle_id}` | `bcn`, `bvh_discipline`, `bvh_hr` | Cập nhật kỳ khi chưa khóa. |
| `POST` | `/cycles/{cycle_id}/submit-review` | `bvh_discipline`, `bvh_hr` | Chuyển sang trạng thái member review. |
| `POST` | `/cycles/{cycle_id}/approve` | `bcn` | Phê duyệt kỳ đánh giá. |
| `POST` | `/cycles/{cycle_id}/lock` | `bcn` | Khóa kỳ đánh giá. |
| `POST` | `/cycles/{cycle_id}/cancel` | `bcn` | Hủy kỳ đánh giá. |

## 7.2. Criteria

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `POST` | `/criteria/seed` | `bcn`, `bvh_discipline` | Seed tiêu chí lõi. |
| `GET` | `/criteria` | authenticated | Danh sách tiêu chí. |
| `GET` | `/criteria/{criterion_id}` | authenticated | Chi tiết tiêu chí. |
| `POST` | `/criteria` | `bcn`, `bvh_discipline` | Tạo tiêu chí tùy chỉnh. |
| `PATCH` | `/criteria/{criterion_id}` | `bcn`, `bvh_discipline` | Cập nhật tiêu chí. |
| `PATCH` | `/criteria/{criterion_id}/status` | `bcn`, `bvh_discipline` | Bật/tắt tiêu chí. |

## 7.3. Member roles and multi-unit weights

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `POST` | `/cycles/{cycle_id}/member-roles` | `bcn`, `bvh_hr`, `bvh_discipline` | Ghi nhận Ban chính/Ban phụ/trọng số. |
| `GET` | `/cycles/{cycle_id}/member-roles` | `bcn`, `bvh_hr`, `bvh_discipline` | Danh sách phân vai trò trong kỳ. |
| `GET` | `/cycles/{cycle_id}/members/{member_id}/roles` | manager hoặc chính member | Xem vai trò của một thành viên. |
| `PATCH` | `/member-roles/{role_id}` | `bcn`, `bvh_hr`, `bvh_discipline` | Cập nhật trọng số/vai trò. |
| `DELETE` | `/member-roles/{role_id}` | `bcn`, `bvh_hr` | Xóa phân vai trò khi chưa khóa kỳ. |

## 7.4. Score events and evidence

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `POST` | `/cycles/{cycle_id}/score-events` | `bcn`, `bvh_discipline`, `bvh_hr`, `bcm` | Ghi nhận điểm cộng/trừ. |
| `GET` | `/cycles/{cycle_id}/score-events` | manager hoặc chính member nếu filter bản thân | Danh sách score events. |
| `PATCH` | `/score-events/{event_id}/void` | `bcn`, `bvh_discipline` | Hủy score event, không hard delete. |
| `POST` | `/cycles/{cycle_id}/evidence` | authorized recorder hoặc member | Gắn minh chứng. |
| `GET` | `/cycles/{cycle_id}/evidence` | manager hoặc chính member nếu filter bản thân | Danh sách minh chứng. |
| `PATCH` | `/evidence/{evidence_id}/verify` | `bcn`, `bvh_discipline`, `bvh_hr`, `bcm` | Xác minh minh chứng. |
| `PATCH` | `/evidence/{evidence_id}/reject` | `bcn`, `bvh_discipline`, `bvh_hr`, `bcm` | Từ chối minh chứng. |

## 7.5. Compute and results

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `POST` | `/cycles/{cycle_id}/compute` | `bcn`, `bvh_discipline`, `bvh_hr` | Tính toàn kỳ. |
| `POST` | `/cycles/{cycle_id}/members/{member_id}/compute` | `bcn`, `bvh_discipline`, `bvh_hr` | Tính lại một thành viên. |
| `GET` | `/cycles/{cycle_id}/members` | manager roles | Danh sách kết quả. |
| `GET` | `/cycles/{cycle_id}/members/{member_id}` | manager hoặc chính member | Chi tiết kết quả thành viên. |
| `GET` | `/cycles/{cycle_id}/members/{member_id}/breakdowns` | manager hoặc chính member | Breakdown theo tiêu chí. |
| `GET` | `/cycles/{cycle_id}/summary` | `bcn`, `bvh_discipline`, `bvh_hr` | Tổng quan kỳ đánh giá. |

## 7.6. Sync endpoints

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `POST` | `/cycles/{cycle_id}/sync/attendance/{meeting_id}` | `bcn`, `bvh_discipline` | Tạo score events từ attendance. |
| `POST` | `/cycles/{cycle_id}/sync/competition/{competition_id}` | `bcn`, `bvh_discipline`, `bcm` | Tạo score events từ competition. |

## 7.7. Appeal endpoint khung

Phase 3 chỉ tạo endpoint nền. Workflow chi tiết thuộc Phase 4.

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `POST` | `/cycles/{cycle_id}/appeals` | `member` hoặc manager tạo thay | Gửi đối soát. |
| `GET` | `/cycles/{cycle_id}/appeals` | manager hoặc chính member nếu filter bản thân | Danh sách đối soát. |
| `GET` | `/appeals/{appeal_id}` | manager hoặc chủ thể liên quan | Chi tiết đối soát. |

## 8. Request schemas đề xuất

Có thể đặt trong `app/schemas.py` hoặc `app/schemas_evaluation.py`.

## 8.1. Cycle schemas

```python
class EvaluationCycleCreate(BaseModel):
    code: str
    name: str
    type: str
    startDate: dt_date
    endDate: dt_date
    description: str | None = None


class EvaluationCycleUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    startDate: dt_date | None = None
    endDate: dt_date | None = None
    description: str | None = None
    status: str | None = None
```

Validation:

- `startDate <= endDate`.
- `code` không trùng.
- Không update nếu cycle đã `LOCKED`.

## 8.2. Criteria schemas

```python
class EvaluationCriteriaCreate(BaseModel):
    code: str
    name: str
    component: str
    unitScope: str = "ALL"
    unitCode: str | None = None
    maxScore: float = Field(gt=0)
    scoreMethod: str
    requiresEvidence: bool = True
    sortOrder: int = 0
    effectiveFrom: dt_date | None = None
    effectiveTo: dt_date | None = None
    description: str | None = None
    metadata: dict | None = None


class EvaluationCriteriaUpdate(BaseModel):
    name: str | None = None
    maxScore: float | None = Field(default=None, gt=0)
    scoreMethod: str | None = None
    requiresEvidence: bool | None = None
    isActive: bool | None = None
    sortOrder: int | None = None
    description: str | None = None
    metadata: dict | None = None
```

## 8.3. Score event schemas

```python
class EvaluationScoreEventCreate(BaseModel):
    memberId: str
    criterionId: str | None = None
    criterionCode: str
    unitCode: str | None = None
    eventType: str
    sourceType: str | None = None
    sourceId: str | None = None
    rawValue: float | None = None
    scoreDelta: float
    weight: float | None = None
    note: str | None = None
    metadata: dict | None = None
```

Validation:

- `scoreDelta` có thể âm hoặc dương tùy `eventType`.
- Nếu `eventType=PENALTY`, `scoreDelta` nên âm hoặc service chuẩn hóa về âm.
- Nếu `criterionCode` yêu cầu evidence, endpoint có thể cho tạo event trước nhưng không được compute approval nếu thiếu evidence.
- Nếu có `sourceType` và `sourceId`, phải áp idempotency rule.

## 8.4. Evidence schemas

```python
class EvaluationEvidenceCreate(BaseModel):
    memberId: str
    criterionId: str | None = None
    criterionCode: str | None = None
    scoreEventId: str | None = None
    evidenceType: str
    title: str
    url: str | None = None
    filePath: str | None = None
    description: str | None = None
    capturedAt: dt_datetime | None = None
    metadata: dict | None = None
```

Validation:

- Phải có ít nhất một trong `url`, `filePath`, `description`.
- Nếu gắn với `scoreEventId`, member/cycle của evidence phải khớp event.
- Member không được gắn evidence cho người khác, trừ manager roles.

## 8.5. Member role schemas

```python
class MemberCycleRoleCreate(BaseModel):
    memberId: str
    unitCode: str
    roleType: str
    roleTitle: str | None = None
    participationWeight: float = Field(ge=0, le=1)
    isPrimary: bool = False
    note: str | None = None
    metadata: dict | None = None
```

Validation:

- Một thành viên trong một kỳ chỉ có một `isPrimary=True`.
- Tổng `participationWeight` theo `cycleId + memberId` phải bằng 1.0 khi dùng cho compute chính thức.
- `unitCode` phải nằm trong danh sách unit code hợp lệ.

## 8.6. Compute schemas

```python
class EvaluationComputeRequest(BaseModel):
    strict: bool = True
    evidenceMode: str = "approval"
    recomputeExisting: bool = True


class EvaluationComputeResponse(BaseModel):
    cycleId: str
    computedMembers: int
    skippedMembers: int
    failedMembers: int
    warnings: list[dict] = Field(default_factory=list)
```

## 9. Response shape đề xuất

Repo hiện có helper `api_response`; Phase 3 nên dùng cùng convention.

Ví dụ thành công:

```json
{
  "success": true,
  "data": {
    "id": "...",
    "code": "2026-05-MONTHLY",
    "name": "Đánh giá tháng 05/2026",
    "status": "DRAFT"
  },
  "meta": null
}
```

Ví dụ lỗi nghiệp vụ:

```json
{
  "success": false,
  "error": {
    "code": "EVALUATION_CYCLE_LOCKED",
    "message": "Evaluation cycle is locked",
    "details": {
      "cycleId": "..."
    }
  }
}
```

Nếu helper response hiện tại chưa hỗ trợ error object, có thể dùng `HTTPException(detail={...})` trong Phase 3 và chuẩn hóa sâu hơn ở phase hardening.

## 10. Output mappers

Không trả SQLAlchemy model trực tiếp. Tạo mapper functions trong router hoặc file riêng.

Ví dụ:

```python
def _cycle_out(cycle: EvaluationCycle) -> dict:
    return {
        "id": cycle.id,
        "code": cycle.code,
        "name": cycle.name,
        "type": cycle.type,
        "startDate": cycle.start_date,
        "endDate": cycle.end_date,
        "status": cycle.status,
        "description": cycle.description,
        "approvedAt": cycle.approved_at,
        "lockedAt": cycle.locked_at,
        "createdAt": cycle.created_at,
        "updatedAt": cycle.updated_at,
    }
```

Mapper cần nhất quán camelCase ở response vì các schema hiện tại của repo đang dùng camelCase ở nhiều module.

## 11. RBAC policy

## 11.1. Role groups

```python
EVALUATION_ADMIN_ROLES = {"bcn"}
EVALUATION_OPERATOR_ROLES = {"bcn", "bvh_discipline", "bvh_hr"}
EVALUATION_RECORDER_ROLES = {"bcn", "bvh_discipline", "bvh_hr", "bcm"}
EVALUATION_VIEWER_ROLES = {"bcn", "bvh_discipline", "bvh_hr", "bcm"}
```

## 11.2. Permission matrix

| Action | Roles |
|---|---|
| Create/update cycle | `bcn`, `bvh_discipline`, `bvh_hr` |
| Approve/lock cycle | `bcn` |
| Seed/create criteria | `bcn`, `bvh_discipline` |
| Create score event | `bcn`, `bvh_discipline`, `bvh_hr`, `bcm` |
| Void score event | `bcn`, `bvh_discipline` |
| Create evidence | recorder roles hoặc chính member |
| Verify evidence | `bcn`, `bvh_discipline`, `bvh_hr`, `bcm` |
| Compute | `bcn`, `bvh_discipline`, `bvh_hr` |
| View all results | `bcn`, `bvh_discipline`, `bvh_hr` |
| View unit results | `bcm` theo unit được phân quyền |
| View own result | chính member |

## 11.3. Unit-level permission

Role `bcm` hiện chưa đủ để xác định phụ trách Ban/Tổ nào. Phase 3 cần chuẩn bị extension point:

```python
def can_access_member_in_cycle(current_user: User, cycle_id: str, member_id: str, db: Session) -> bool:
    if current_user.has_any_roles({"bcn", "bvh_discipline", "bvh_hr"}):
        return True
    if is_current_user_linked_to_member(current_user, member_id):
        return True
    if current_user.has_role("bcm"):
        return can_access_unit_scope(current_user, cycle_id, member_id, db)
    return False
```

Nếu chưa có bảng liên kết user-member hoặc user-unit, Phase 3 có thể tạm giới hạn `bcm` xem danh sách theo query `unitCode`, còn việc enforce unit ownership hoàn chỉnh chuyển sang phase RBAC hardening.

## 12. Error mapping

| Domain error | HTTP status | Error code |
|---|---:|---|
| `EvaluationCycleLockedError` | 409 | `EVALUATION_CYCLE_LOCKED` |
| `EvaluationMissingCriteriaError` | 422 | `EVALUATION_MISSING_CRITERIA` |
| `EvaluationEvidenceError` | 422 | `EVALUATION_EVIDENCE_ERROR` |
| `EvaluationWeightError` | 422 | `EVALUATION_WEIGHT_ERROR` |
| Not found | 404 | `RESOURCE_NOT_FOUND` |
| Forbidden | 403 | `FORBIDDEN` |
| Duplicate | 409 | `DUPLICATE_RESOURCE` |

Helper đề xuất:

```python
def raise_evaluation_error(exc: EvaluationError) -> None:
    status_code = EVALUATION_ERROR_STATUS_MAP.get(exc.code, 400)
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "message": str(exc),
            "details": getattr(exc, "details", None),
        },
    )
```

## 13. Endpoint design chi tiết

## 13.1. `POST /api/v2/evaluations/cycles`

Tạo kỳ đánh giá.

Request:

```json
{
  "code": "2026-05-MONTHLY",
  "name": "Đánh giá tháng 05/2026",
  "type": "MONTHLY",
  "startDate": "2026-05-01",
  "endDate": "2026-05-31",
  "description": "Kỳ đánh giá thử nghiệm"
}
```

Response data:

```json
{
  "id": "...",
  "code": "2026-05-MONTHLY",
  "name": "Đánh giá tháng 05/2026",
  "type": "MONTHLY",
  "status": "DRAFT",
  "startDate": "2026-05-01",
  "endDate": "2026-05-31"
}
```

Rules:

- Chỉ `bcn`, `bvh_discipline`, `bvh_hr`.
- `code` unique.
- `startDate <= endDate`.

## 13.2. `POST /api/v2/evaluations/criteria/seed`

Seed tiêu chí lõi.

Request:

```json
{
  "version": "2026",
  "overwrite": false
}
```

Response:

```json
{
  "version": "2026",
  "created": 14,
  "updated": 0,
  "skipped": 0
}
```

Rules:

- Chỉ `bcn`, `bvh_discipline`.
- Idempotent: gọi lại không tạo duplicate.

## 13.3. `POST /api/v2/evaluations/cycles/{cycle_id}/score-events`

Ghi nhận score event.

Request:

```json
{
  "memberId": "...",
  "criterionCode": "I.2",
  "eventType": "PENALTY",
  "sourceType": "ATTENDANCE",
  "sourceId": "attendance-id-or-meeting-id",
  "scoreDelta": -2,
  "note": "Báo vắng muộn"
}
```

Rules:

- Cycle không được `LOCKED`.
- User phải có quyền ghi nhận.
- Nếu có `sourceType/sourceId`, áp idempotency.
- Nếu tiêu chí yêu cầu minh chứng, event có thể được tạo nhưng compute strict sẽ fail nếu chưa có evidence.

## 13.4. `POST /api/v2/evaluations/cycles/{cycle_id}/evidence`

Gắn minh chứng.

Request:

```json
{
  "memberId": "...",
  "criterionCode": "I.2",
  "scoreEventId": "...",
  "evidenceType": "LINK",
  "title": "Biên bản báo vắng",
  "url": "https://example.com/evidence",
  "description": "Tin nhắn báo vắng trước cuộc họp"
}
```

Rules:

- Chính member có thể nộp evidence cho mình.
- Recorder/manager có thể nộp evidence cho member thuộc phạm vi quyền.
- Nếu evidence gắn với score event, cycle/member phải khớp.

## 13.5. `POST /api/v2/evaluations/cycles/{cycle_id}/compute`

Tính điểm toàn kỳ.

Request:

```json
{
  "strict": true,
  "evidenceMode": "approval",
  "recomputeExisting": true
}
```

Response:

```json
{
  "cycleId": "...",
  "computedMembers": 42,
  "skippedMembers": 0,
  "failedMembers": 0,
  "warnings": []
}
```

Rules:

- Chỉ `bcn`, `bvh_discipline`, `bvh_hr`.
- Cycle không được `LOCKED`.
- Nếu `strict=true`, lỗi một member có thể làm fail toàn bộ compute.
- Nếu `strict=false`, trả danh sách failed/warnings.

## 13.6. `GET /api/v2/evaluations/cycles/{cycle_id}/members/{member_id}`

Xem kết quả đánh giá của thành viên.

Response data:

```json
{
  "id": "...",
  "cycleId": "...",
  "memberId": "...",
  "componentIScore": 27,
  "componentIIScore": 18,
  "componentIIiAScore": 25,
  "componentIIiBScore": 17.4,
  "totalScore": 87.4,
  "preliminaryClassification": "GOOD",
  "finalClassification": "GOOD",
  "attendanceRate": 0.92,
  "blockers": [],
  "status": "COMPUTED"
}
```

Rules:

- Manager roles xem được theo phạm vi quyền.
- Member chỉ xem được của mình.

## 14. Pagination và filter

Các endpoint list nên dùng convention hiện có:

```text
page
pageSize
```

Filters đề xuất:

### `GET /cycles`

```text
status
type
fromDate
toDate
search
```

### `GET /criteria`

```text
component
unitCode
isActive
search
```

### `GET /cycles/{cycle_id}/members`

```text
memberSearch
unitCode
classification
status
minScore
maxScore
```

### `GET /cycles/{cycle_id}/score-events`

```text
memberId
criterionCode
component
unitCode
eventType
sourceType
isVoid
```

### `GET /cycles/{cycle_id}/evidence`

```text
memberId
criterionCode
evidenceType
status
```

## 15. Audit log requirements

Endpoint mutating cần ghi audit log hoặc gọi service đã ghi audit log.

| Endpoint | Action |
|---|---|
| Create cycle | `CREATE_EVALUATION_CYCLE` |
| Update cycle | `UPDATE_EVALUATION_CYCLE` |
| Approve cycle | `APPROVE_EVALUATION_CYCLE` |
| Lock cycle | `LOCK_EVALUATION_CYCLE` |
| Seed criteria | `SEED_EVALUATION_CRITERIA` |
| Create score event | `CREATE_EVALUATION_SCORE_EVENT` |
| Void score event | `VOID_EVALUATION_SCORE_EVENT` |
| Create evidence | `CREATE_EVALUATION_EVIDENCE` |
| Verify evidence | `VERIFY_EVALUATION_EVIDENCE` |
| Compute cycle | `COMPUTE_CYCLE_EVALUATION` |
| Compute member | `COMPUTE_MEMBER_EVALUATION` |
| Sync attendance | `SYNC_ATTENDANCE_SCORE_EVENTS` |
| Sync competition | `SYNC_COMPETITION_SCORE_EVENTS` |

## 16. Implementation skeleton

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.response import api_response
from app.core.rbac import require_roles
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services.evaluation_calculator import EvaluationCalculatorService
from app.services.evaluation_criteria_seed import EvaluationCriteriaSeedService

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/cycles/{cycle_id}/compute")
def compute_cycle(
    cycle_id: str,
    body: EvaluationComputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("bcn", "bvh_discipline", "bvh_hr")),
) -> dict:
    service = EvaluationCalculatorService(db)
    try:
        result = service.compute_cycle(
            cycle_id,
            actor_user_id=current_user.id,
            strict=body.strict,
            evidence_mode=body.evidenceMode,
            recompute_existing=body.recomputeExisting,
        )
    except EvaluationError as exc:
        raise_evaluation_http_error(exc)
    return api_response(data=result)
```

## 17. Integration tests

File đề xuất:

```text
tests/test_evaluation_api_v2.py
```

## 17.1. Cycle endpoint tests

| Test | Mục tiêu |
|---|---|
| `test_create_cycle_requires_operator_role` | Member thường không tạo được kỳ. |
| `test_create_cycle_success` | Operator tạo được kỳ. |
| `test_create_cycle_rejects_invalid_date_range` | `startDate > endDate` bị từ chối. |
| `test_create_cycle_rejects_duplicate_code` | Không cho trùng code. |
| `test_lock_cycle_requires_bcn` | Chỉ BCN khóa kỳ. |

## 17.2. Criteria endpoint tests

| Test | Mục tiêu |
|---|---|
| `test_seed_criteria_is_idempotent` | Seed nhiều lần không duplicate. |
| `test_create_criterion_requires_admin_or_discipline` | Role không hợp lệ bị 403. |
| `test_list_criteria_filters_by_component` | Filter component hoạt động. |

## 17.3. Score event/evidence tests

| Test | Mục tiêu |
|---|---|
| `test_create_score_event_requires_recorder_role` | Member thường không ghi điểm người khác. |
| `test_create_score_event_success` | Recorder ghi điểm thành công. |
| `test_create_score_event_rejects_locked_cycle` | Kỳ khóa không nhận event mới. |
| `test_create_evidence_for_own_member` | Member nộp minh chứng cho mình. |
| `test_evidence_response_filters_sensitive_metadata` | Evidence response không trả metadata nhạy cảm. |
| `test_verify_evidence_requires_manager_role` | Member không tự verify evidence. |
| `test_verify_evidence_rejects_self_review` | Người nộp minh chứng không tự verify. |
| `test_void_score_event_does_not_delete_event` | Void event không hard delete. |

## 17.4. Compute/results tests

| Test | Mục tiêu |
|---|---|
| `test_compute_cycle_requires_operator_role` | Role thường bị 403. |
| `test_compute_cycle_success` | Compute tạo `member_evaluations`. |
| `test_compute_cycle_maps_weight_error_to_422` | Lỗi trọng số trả 422. |
| `test_get_member_result_allows_owner` | Member xem được điểm của mình. |
| `test_get_member_result_denies_other_member` | Member không xem điểm người khác. |
| `test_get_cycle_members_requires_manager` | Danh sách toàn kỳ không mở cho member thường. |

## 17.5. Appeal tests

| Test | Mục tiêu |
|---|---|
| `test_create_appeal_rejects_locked_cycle` | Kỳ khóa không nhận appeal mới. |

## 18. OpenAPI quality checklist

- [x] Endpoint có tag `evaluations`.
- [x] Request body dùng Pydantic schema, không dùng raw dict nếu không cần.
- [x] Field camelCase ở request/response để phù hợp frontend.
- [x] Các endpoint list có `page`, `pageSize`.
- [x] Error response được mô tả nhất quán.
- [x] Không expose internal SQLAlchemy field name nếu response đang dùng camelCase.

## 19. Security checklist

- [x] Mọi endpoint `/api/v2/evaluations` yêu cầu authenticated user.
- [x] Mutating endpoint có role guard.
- [x] Member không xem/sửa dữ liệu người khác.
- [x] Không cho thao tác trên cycle `LOCKED`, trừ endpoint read.
- [x] Không cho verify evidence bởi chính người nộp nếu policy yêu cầu độc lập.
- [x] Không trả metadata nhạy cảm nếu evidence chứa internal link.
- [x] Không cho client tự set `recordedByUserId`, `approvedByUserId`, `verifiedByUserId`; server lấy từ token.

## 20. Migration compatibility

Phase 3 không tạo migration mới nếu Phase 1 đã đủ schema. Nếu phát hiện thiếu cột phục vụ API, phải:

1. cập nhật tài liệu Phase 1;
2. tạo migration bổ sung riêng;
3. không sửa trực tiếp migration đã chạy ở môi trường khác nếu đã được dùng.

## 21. Definition of Done

Phase 3 hoàn thành khi:

- `/api/v2/evaluations` được mount trong `api_v2_router`.
- Tạo/xem/cập nhật cycle hoạt động.
- Seed/list criteria hoạt động.
- Tạo/void score event hoạt động.
- Tạo/verify/reject evidence hoạt động.
- Ghi nhận member roles hoạt động.
- Compute cycle/member gọi đúng service Phase 2.
- Xem kết quả member và breakdown hoạt động theo quyền.
- Sync attendance/competition gọi đúng `EvaluationSyncService`.
- Domain errors được map đúng HTTP status.
- Có integration tests cho endpoint chính.
- API v1 legacy không bị thay đổi hành vi.
- Swagger/OpenAPI hiển thị được nhóm endpoint mới.

### 21.1. Trạng thái triển khai

- [x] Tạo `app/schemas_evaluation.py` cho request schema Phase 3.
- [x] Tạo `app/routers/v2/evaluations.py` và mount vào `api_v2_router`.
- [x] Expose endpoint nền cho cycles, criteria, member roles, score events, evidence, compute/results, sync và appeal.
- [x] Router chỉ xử lý auth/RBAC/validation/response mapping; tính điểm và sync vẫn gọi service Phase 2.
- [x] Domain errors được map sang HTTP status và `detail={code, message}`.
- [x] Guard cycle `LOCKED`, self-review evidence, owner access và metadata evidence nhạy cảm.
- [x] Bổ sung integration tests trong `tests/test_evaluation_api_v2.py`.
- [x] Đã chạy targeted ruff và pytest cho Phase 3 + bộ service Phase 2.

## 22. Thứ tự triển khai đề xuất

1. Tạo schemas cho Evaluation API.
2. Tạo helper error mapping.
3. Tạo `app/routers/v2/evaluations.py` với endpoint cycle trước.
4. Mount router trong `app/routers/v2/__init__.py`.
5. Tạo endpoint criteria seed/list.
6. Tạo endpoint score event/evidence.
7. Tạo endpoint member roles.
8. Tạo endpoint compute/results.
9. Tạo endpoint sync attendance/competition.
10. Tạo endpoint appeal khung.
11. Viết integration tests.
12. Chạy `pytest` và `ruff check .`.

## 23. Ghi chú chuyển tiếp sang Phase 4

Phase 4 sẽ hoàn thiện workflow đối soát và phê duyệt:

- trạng thái member review;
- thời hạn đối soát;
- member appeal lifecycle;
- xử lý appeal bởi Ban Vận hành/Ban chuyên môn/BCN;
- điều chỉnh điểm sau appeal;
- approve và lock cycle theo quy trình chính thức.

Phase 3 chỉ cần tạo endpoint nền để không phải thay đổi lớn ở routing khi sang Phase 4.
