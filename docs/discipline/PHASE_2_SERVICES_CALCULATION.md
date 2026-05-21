# Phase 2 Implementation Guide - Evaluation Services & Calculation Engine

## 1. Mục tiêu Phase 2

Phase 2 xây dựng tầng service và calculation engine cho module `evaluations`. Mục tiêu là biến schema đã thiết kế ở Phase 1 thành một lõi nghiệp vụ có thể tính điểm, kiểm tra minh chứng, áp dụng giới hạn điểm, áp dụng điều kiện chặn xếp loại và tạo kết quả tổng hợp có thể giải trình.

Phase này chưa bắt buộc mở đầy đủ API public cho frontend. API v2 hoàn chỉnh thuộc Phase 3. Tuy nhiên, service trong Phase 2 phải được thiết kế đủ rõ để Phase 3 chỉ cần gọi lại, không viết lại logic nghiệp vụ trong router.

## 2. Đầu vào của Phase 2

Phase 2 giả định Phase 1 đã hoàn thành các bảng lõi:

- `evaluation_cycles`
- `evaluation_criteria`
- `evaluation_score_events`
- `evaluation_evidence`
- `member_evaluations`
- `member_evaluation_breakdowns`
- `member_cycle_roles`
- `evaluation_appeals`
- `discipline_cases`

Các bảng legacy vẫn được giữ nguyên:

- `discipline_records`
- `members`
- `meetings`
- `attendances`
- `competitions`
- `competition_results`

## 3. Phạm vi thực hiện

### 3.1. Trong phạm vi

| Hạng mục | Mục tiêu |
|---|---|
| Calculator service | Tính điểm theo tiêu chí, cấu phần và tổng điểm. |
| Classification policy | Xếp loại theo tổng điểm và điều kiện chặn. |
| Evidence validation | Kiểm tra yêu cầu minh chứng cho score events. |
| Criteria seed | Chuẩn bị seed tiêu chí theo quy chế. |
| Score capping | Bảo đảm điểm không âm và không vượt trần tiêu chí/cấu phần. |
| Multi-unit weighting | Tính III-B cho thành viên đa ban theo trọng số. |
| Idempotency policy | Định nghĩa cách chống cộng trùng khi sync attendance/competition/task. |
| Unit test | Kiểm thử công thức tính điểm và policy độc lập với API. |

### 3.2. Ngoài phạm vi

| Hạng mục | Lý do |
|---|---|
| API v2 hoàn chỉnh | Thuộc Phase 3. |
| Workflow đối soát đầy đủ | Thuộc Phase 4. |
| Migration dữ liệu legacy | Thuộc Phase 5. |
| UI hoặc dashboard | Thuộc frontend phase. |
| Export báo cáo | Thực hiện sau khi calculation engine ổn định. |

## 4. Nguyên tắc thiết kế service

1. Router không chứa công thức tính điểm.
2. Service phải deterministic: cùng input phải cho cùng output.
3. Không xóa score event đã ghi nhận; chỉ dùng `is_void=True` nếu cần hủy.
4. Điểm tổng hợp trong `member_evaluations` phải có thể tái tính từ `evaluation_score_events`, `evaluation_criteria`, `member_cycle_roles`, `discipline_cases` và `evaluation_evidence`.
5. Mọi điểm cộng/trừ phải gắn được với tiêu chí.
6. Điểm vượt trần phải bị cap ở cấp tiêu chí và cấp cấu phần.
7. Điều kiện chặn không làm thay đổi `total_score`; nó chỉ làm thay đổi `final_classification`.
8. III-B đa ban được tính bằng weighted average theo trọng số tham gia, không cộng chồng nhiều Ban/Tổ vượt quá 20 điểm.
9. Service không phụ thuộc FastAPI request object.
10. Error nghiệp vụ cần có code ổn định để Phase 3 map sang response chuẩn.

## 5. File cần tạo hoặc chỉnh sửa

```text
app/services/evaluation_calculator.py
app/services/evaluation_classification.py
app/services/evaluation_evidence.py
app/services/evaluation_criteria_seed.py
app/services/evaluation_sync.py
app/core/evaluation_constants.py
tests/test_evaluation_calculator.py
tests/test_evaluation_classification.py
tests/test_evaluation_evidence.py
tests/test_evaluation_sync_policy.py
docs/discipline/PHASE_2_SERVICES_CALCULATION.md
```

Ghi chú:

- Nếu repo chưa có thư mục `app/services`, tạo mới.
- Nếu đã có service khác, giữ cùng style import và transaction.
- Không nên chỉnh router v1 `app/routers/discipline.py` trong Phase 2, trừ khi cần fix lỗi nghiêm trọng độc lập.

## 6. Constants và domain codes

File đề xuất:

```text
app/core/evaluation_constants.py
```

Nội dung chính:

```python
COMPONENT_I = "I"
COMPONENT_II = "II"
COMPONENT_III_A = "III_A"
COMPONENT_III_B = "III_B"

COMPONENT_MAX_SCORES = {
    COMPONENT_I: 30.0,
    COMPONENT_II: 20.0,
    COMPONENT_III_A: 30.0,
    COMPONENT_III_B: 20.0,
}

TOTAL_MAX_SCORE = 100.0

CLASSIFICATION_EXCELLENT = "EXCELLENT"
CLASSIFICATION_GOOD = "GOOD"
CLASSIFICATION_PASSED = "PASSED"
CLASSIFICATION_NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT"
CLASSIFICATION_FAILED = "FAILED"

CYCLE_STATUS_LOCKED = "LOCKED"
EVIDENCE_STATUS_VERIFIED = "VERIFIED"
```

Không nên để string rải rác trong service.

## 7. Service 1 - `EvaluationCalculatorService`

File:

```text
app/services/evaluation_calculator.py
```

### 7.1. Trách nhiệm

`EvaluationCalculatorService` chịu trách nhiệm:

- lấy dữ liệu score events hợp lệ trong một kỳ;
- gom điểm theo thành viên;
- gom điểm theo tiêu chí;
- cap điểm theo `max_score` của tiêu chí;
- cap điểm theo trần cấu phần;
- tính III-B đa ban theo trọng số;
- tạo hoặc cập nhật `member_evaluations`;
- tạo hoặc cập nhật `member_evaluation_breakdowns`;
- gọi `ClassificationPolicyService` để xác định xếp loại sơ bộ và xếp loại cuối.

### 7.2. Public methods đề xuất

```python
class EvaluationCalculatorService:
    def __init__(self, db: Session):
        self.db = db

    def compute_cycle(self, cycle_id: str, *, actor_user_id: str | None = None) -> dict:
        ...

    def compute_member(self, cycle_id: str, member_id: str, *, actor_user_id: str | None = None) -> dict:
        ...

    def preview_member(self, cycle_id: str, member_id: str) -> dict:
        ...
```

Ý nghĩa:

| Method | Ghi DB | Mục đích |
|---|---:|---|
| `compute_cycle` | Có | Tính toàn bộ thành viên trong kỳ. |
| `compute_member` | Có | Tính lại một thành viên. |
| `preview_member` | Không | Xem trước kết quả, phục vụ test hoặc preview API. |

### 7.3. Dữ liệu đầu vào

- `evaluation_cycles`: kỳ đánh giá.
- `evaluation_criteria`: tiêu chí đang active trong kỳ.
- `evaluation_score_events`: điểm/dữ liệu đầu vào, bỏ qua `is_void=True`.
- `evaluation_evidence`: số lượng minh chứng liên quan.
- `member_cycle_roles`: trọng số Ban/Tổ.
- `discipline_cases`: điều kiện chặn.

### 7.4. Dữ liệu đầu ra

- `member_evaluations`.
- `member_evaluation_breakdowns`.
- Summary object trả về cho caller.

Ví dụ output:

```json
{
  "cycleId": "...",
  "computedMembers": 42,
  "skippedMembers": 0,
  "calculationVersion": "evaluation-v1.0.0"
}
```

## 8. Công thức tính điểm

### 8.1. Tính điểm theo tiêu chí

Với mỗi thành viên và mỗi tiêu chí:

```text
raw_criterion_score = sum(score_delta of valid score events)
criterion_score = min(max(raw_criterion_score, 0), criterion.max_score)
```

Trong đó:

- valid score event là event có `is_void=False`;
- nếu tiêu chí yêu cầu minh chứng, service phải kiểm tra evidence trước khi tính;
- event thiếu minh chứng có thể bị bỏ qua hoặc raise lỗi tùy mode.

Mode đề xuất:

| Mode | Cách xử lý event thiếu minh chứng |
|---|---|
| `strict` | Raise error, không compute. |
| `lenient` | Bỏ qua event thiếu minh chứng và ghi warning. |

Phase 2 nên mặc định dùng `strict` trong unit test và dùng `lenient` cho preview nếu cần.

### 8.2. Tính cấu phần I, II, III-A

```text
component_score = sum(final criterion scores of that component)
component_score = min(max(component_score, 0), component_max_score)
```

Trần cấu phần:

| Component | Max |
|---|---:|
| I | 30 |
| II | 20 |
| III_A | 30 |
| III_B | 20 |

### 8.3. Tính III-B cho thành viên một Ban/Tổ

Nếu thành viên chỉ có một unit role chính:

```text
component_iii_b_score = sum(final criterion scores where component = III_B and unit_code = member.primary_unit)
component_iii_b_score = min(max(component_iii_b_score, 0), 20)
```

### 8.4. Tính III-B cho thành viên đa ban

Với mỗi Ban/Tổ thành viên tham gia:

```text
unit_score_20 = min(max(sum(III_B criteria scores of that unit), 0), 20)
weighted_unit_score = unit_score_20 * participation_weight
component_iii_b_score = sum(weighted_unit_score)
component_iii_b_score = min(max(component_iii_b_score, 0), 20)
```

Điều kiện:

```text
sum(participation_weight for member in cycle) == 1.0
```

Sai số float cho phép:

```text
abs(total_weight - 1.0) <= 0.001
```

Nếu thiếu role/weight:

| Trường hợp | Cách xử lý đề xuất |
|---|---|
| Không có `member_cycle_roles` | Fallback sang `Member.ban` với weight = 1.0 nếu có. |
| Có nhiều role nhưng tổng weight != 1.0 | Raise `EvaluationWeightError`. |
| Có nhiều role chính | Raise `EvaluationWeightError`. |
| Có unit không có score event | Tính unit đó bằng 0. |

### 8.5. Tổng điểm

```text
total_score = component_i_score + component_ii_score + component_iii_a_score + component_iii_b_score
total_score = min(max(total_score, 0), 100)
```

## 9. Service 2 - `ClassificationPolicyService`

File:

```text
app/services/evaluation_classification.py
```

### 9.1. Trách nhiệm

- Xác định xếp loại sơ bộ theo tổng điểm.
- Đọc danh sách blocker từ dữ liệu đã tính và `discipline_cases`.
- Hạ xếp loại theo trần nếu có điều kiện chặn.
- Trả về `preliminary_classification`, `final_classification`, `blockers`.

### 9.2. Public methods đề xuất

```python
class ClassificationPolicyService:
    def classify_preliminary(self, total_score: float) -> str:
        ...

    def apply_blockers(self, preliminary: str, blockers: list[dict]) -> str:
        ...

    def collect_blockers(self, *, cycle_id: str, member_id: str, attendance_rate: float | None) -> list[dict]:
        ...
```

### 9.3. Bảng xếp loại sơ bộ

| Điều kiện điểm | Code | Label |
|---|---|---|
| `90 <= score <= 100` | `EXCELLENT` | Xuất sắc |
| `80 <= score < 90` | `GOOD` | Tốt |
| `65 <= score < 80` | `PASSED` | Đạt |
| `50 <= score < 65` | `NEEDS_IMPROVEMENT` | Cần cải thiện |
| `score < 50` | `FAILED` | Không đạt |

### 9.4. Blocker policy

| Blocker code | Điều kiện | Classification cap |
|---|---|---|
| `UNEXCUSED_ABSENCE` | Có vắng không phép trong kỳ | `GOOD` |
| `ATTENDANCE_UNDER_80` | Tỷ lệ chuyên cần < 80% | `PASSED` |
| `REPEATED_LATE_OR_MISSED_DEADLINE` | Trễ hạn/phản hồi chậm lặp lại | `PASSED` |
| `INTERNAL_WARNING` | Có cảnh cáo nội bộ | `NEEDS_IMPROVEMENT` |
| `SEVERE_VIOLATION` | Vi phạm bảo mật, tài chính, dữ liệu, uy tín | `FAILED` |
| `CRITICAL_TASK_FAILED_MULTI_UNIT` | Nhiệm vụ trọng yếu ở một Ban/Tổ không hoàn thành | `GOOD` hoặc thấp hơn tùy case |

Mapping thứ tự xếp loại:

```python
CLASSIFICATION_RANK = {
    "FAILED": 0,
    "NEEDS_IMPROVEMENT": 1,
    "PASSED": 2,
    "GOOD": 3,
    "EXCELLENT": 4,
}
```

Áp dụng cap:

```text
final_classification = min(preliminary_classification, all blocker caps by rank)
```

## 10. Service 3 - `EvidenceValidationService`

File:

```text
app/services/evaluation_evidence.py
```

### 10.1. Trách nhiệm

- Kiểm tra score event có đủ minh chứng nếu tiêu chí yêu cầu.
- Kiểm tra minh chứng có trạng thái hợp lệ.
- Đếm số minh chứng cho breakdown.
- Cung cấp warning/error cho calculator.

### 10.2. Public methods đề xuất

```python
class EvidenceValidationService:
    def count_evidence_for_event(self, score_event_id: str) -> int:
        ...

    def has_valid_evidence_for_event(self, score_event_id: str) -> bool:
        ...

    def validate_score_events(self, events: list[EvaluationScoreEvent], *, strict: bool = True) -> list[dict]:
        ...
```

### 10.3. Evidence hợp lệ

Một evidence được xem là hợp lệ nếu:

```text
status in {PENDING, VERIFIED}
```

Trong giai đoạn tính điểm chính thức, có thể yêu cầu:

```text
status == VERIFIED
```

Đề xuất mode:

| Mode | Evidence status được tính |
|---|---|
| `draft` | `PENDING`, `VERIFIED` |
| `approval` | `VERIFIED` |

## 11. Service 4 - `EvaluationCriteriaSeedService`

File:

```text
app/services/evaluation_criteria_seed.py
```

### 11.1. Trách nhiệm

- Seed tiêu chí từ bộ quy chế chuẩn.
- Không duplicate nếu seed lại nhiều lần.
- Cho phép version hóa bộ tiêu chí.
- Chuẩn bị dữ liệu cho calculator.

### 11.2. Data structure đề xuất

```python
DEFAULT_EVALUATION_CRITERIA_2026 = [
    {
        "code": "I.1",
        "name": "Tỷ lệ tham gia sinh hoạt, họp và hoạt động bắt buộc",
        "component": "I",
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 15.0,
        "score_method": "RATIO",
        "requires_evidence": True,
        "sort_order": 101,
        "metadata": {
            "formula": "attendance_rate * 15",
            "basic_attendance_threshold": 0.8
        },
    },
]
```

### 11.3. Tiêu chí lõi cần seed trước

#### Cấu phần I - Kỷ luật và chuyên cần

| Code | Tên | Max |
|---|---|---:|
| `I.1` | Tỷ lệ tham gia sinh hoạt, họp và hoạt động bắt buộc | 15 |
| `I.2` | Tuân thủ quy trình xin phép và báo cáo vắng mặt | 7 |
| `I.3` | Đúng giờ và tuân thủ thời hạn phản hồi | 4 |
| `I.4` | Hoàn thành nghĩa vụ hành chính bắt buộc | 4 |

#### Cấu phần II - Thái độ và ý thức tổ chức

| Code | Tên | Max |
|---|---|---:|
| `II.1` | Tinh thần trách nhiệm trong công việc | 5 |
| `II.2` | Mức độ chủ động và phối hợp tổ chức | 5 |
| `II.3` | Bảo vệ uy tín, hình ảnh và chuẩn mực phát ngôn của CLB | 5 |
| `II.4` | Bảo mật tài nguyên số và thông tin nội bộ | 5 |

#### Cấu phần III-A - Hiệu suất chuyên môn dùng chung

| Code | Tên | Max |
|---|---|---:|
| `III-A.1` | Hoàn thành nhiệm vụ được phân công | 10 |
| `III-A.2` | Chất lượng sản phẩm đầu ra | 8 |
| `III-A.3` | Tiến độ và khả năng cập nhật công việc | 5 |
| `III-A.4` | Khả năng phối hợp trong nhiệm vụ chuyên môn | 4 |
| `III-A.5` | Cải tiến, học hỏi và đóng góp chuyên môn | 3 |

#### Cấu phần III-B - Đặc thù Ban/Tổ

Phase 2 chỉ cần chuẩn bị cơ chế seed. Danh sách chi tiết từng Ban/Tổ sẽ lấy từ bảng tiêu chí chi tiết và có thể đưa vào seed ở bước sau.

Unit code cần hỗ trợ:

| Unit code | Đơn vị |
|---|---|
| `BCN` | Ban Chủ nhiệm |
| `BCNg` | Ban Công nghệ |
| `BTT` | Ban Truyền thông |
| `BVH_NS` | Ban Vận hành - Tổ Nhân sự |
| `BVH_KL` | Ban Vận hành - Tổ Kỷ luật |
| `BVH_HC` | Ban Vận hành - Tổ Hậu cần |
| `BVH_TC` | Ban Vận hành - Tổ Tài chính |

## 12. Service 5 - `EvaluationSyncService`

File:

```text
app/services/evaluation_sync.py
```

### 12.1. Trách nhiệm

Service này không thay thế toàn bộ sync legacy ngay trong Phase 2. Nó định nghĩa cơ chế chuẩn để Phase 3/5 gọi:

- tạo score events từ attendance;
- tạo score events từ competition/task;
- chống cộng trùng bằng `source_type + source_id + member_id + criterion_code + event_type`;
- không cộng trực tiếp vào `discipline_records.kpi`.

### 12.2. Public methods đề xuất

```python
class EvaluationSyncService:
    def sync_attendance_to_score_events(self, cycle_id: str, meeting_id: str, *, actor_user_id: str | None = None) -> dict:
        ...

    def sync_competition_to_score_events(self, cycle_id: str, competition_id: str, *, actor_user_id: str | None = None) -> dict:
        ...
```

### 12.3. Idempotency rule

Trước khi tạo event, kiểm tra đã tồn tại event chưa:

```text
cycle_id = current cycle
member_id = target member
criterion_code = target criterion
source_type = ATTENDANCE | COMPETITION | TASK | MANUAL
source_id = source object id
event_type = PENALTY | BONUS | BASE | MANUAL_SCORE
is_void = False
```

Nếu đã tồn tại:

- không tạo event mới;
- trả về `skippedCount += 1`;
- không thay đổi điểm.

## 13. Error classes đề xuất

Có thể tạo trong `evaluation_calculator.py` hoặc tách file `app/services/evaluation_errors.py`.

```python
class EvaluationError(Exception):
    code = "EVALUATION_ERROR"


class EvaluationCycleLockedError(EvaluationError):
    code = "EVALUATION_CYCLE_LOCKED"


class EvaluationMissingCriteriaError(EvaluationError):
    code = "EVALUATION_MISSING_CRITERIA"


class EvaluationEvidenceError(EvaluationError):
    code = "EVALUATION_EVIDENCE_ERROR"


class EvaluationWeightError(EvaluationError):
    code = "EVALUATION_WEIGHT_ERROR"
```

Phase 3 sẽ map các error này thành HTTP response chuẩn.

## 14. Pseudocode calculator

```python
def compute_member(cycle_id: str, member_id: str):
    cycle = get_cycle(cycle_id)
    ensure_cycle_not_locked(cycle)

    criteria = load_active_criteria(cycle)
    events = load_valid_score_events(cycle_id, member_id)
    roles = load_member_roles_or_fallback(cycle_id, member_id)

    validate_evidence(events)
    validate_role_weights(roles)

    criterion_scores = {}
    for criterion in criteria:
        related_events = filter_events(events, criterion)
        raw_score = sum(event.score_delta for event in related_events)
        final_score = clamp(raw_score, 0, criterion.max_score)
        criterion_scores[criterion.code, criterion.unit_code] = final_score
        upsert_breakdown(...)

    component_i = clamp(sum_component("I"), 0, 30)
    component_ii = clamp(sum_component("II"), 0, 20)
    component_iii_a = clamp(sum_component("III_A"), 0, 30)
    component_iii_b = compute_weighted_iii_b(criterion_scores, roles)

    total = clamp(component_i + component_ii + component_iii_a + component_iii_b, 0, 100)

    preliminary = classification_policy.classify_preliminary(total)
    blockers = classification_policy.collect_blockers(...)
    final = classification_policy.apply_blockers(preliminary, blockers)

    upsert_member_evaluation(...)
    return result
```

## 15. Transaction policy

### 15.1. `compute_member`

- Có thể chạy trong một DB transaction.
- Xóa hoặc replace breakdown cũ của member trong cycle trước khi ghi breakdown mới.
- Không xóa score events.
- Upsert `member_evaluations` theo unique `(cycle_id, member_id)`.

### 15.2. `compute_cycle`

Có hai lựa chọn:

| Cách | Ưu điểm | Nhược điểm |
|---|---|---|
| Một transaction toàn bộ cycle | Atomic | Dễ rollback lớn nếu một member lỗi. |
| Transaction từng member | Bền hơn khi dữ liệu không sạch | Có thể partial compute. |

Đề xuất Phase 2:

- `compute_cycle(strict=True)`: fail-fast toàn bộ nếu có lỗi.
- `compute_cycle(strict=False)`: compute từng member, lưu lỗi vào summary.

## 16. Audit log policy

Phase 2 service nên chuẩn bị hook audit, nhưng không cần ghi quá nhiều log cho từng breakdown nếu gây nhiễu.

Audit tối thiểu:

| Action | Khi nào ghi |
|---|---|
| `COMPUTE_MEMBER_EVALUATION` | Khi compute một member. |
| `COMPUTE_CYCLE_EVALUATION` | Khi compute toàn kỳ. |
| `SEED_EVALUATION_CRITERIA` | Khi seed tiêu chí. |
| `SYNC_ATTENDANCE_SCORE_EVENTS` | Khi tạo score events từ attendance. |
| `SYNC_COMPETITION_SCORE_EVENTS` | Khi tạo score events từ competition. |

## 17. Test bắt buộc Phase 2

### 17.1. Calculator tests

File:

```text
tests/test_evaluation_calculator.py
```

| Test | Mục tiêu |
|---|---|
| `test_criterion_score_is_capped_by_max_score` | Điểm tiêu chí không vượt max. |
| `test_criterion_score_never_negative` | Điểm tiêu chí không âm. |
| `test_component_scores_are_capped` | I/II/III-A/III-B không vượt trần cấu phần. |
| `test_total_score_is_capped_at_100` | Tổng điểm không vượt 100. |
| `test_compute_single_unit_iii_b` | III-B một Ban/Tổ tính đúng. |
| `test_compute_multi_unit_iii_b_weighted` | III-B đa ban tính đúng theo trọng số. |
| `test_invalid_multi_unit_weight_raises_error` | Tổng trọng số khác 1.0 thì lỗi. |
| `test_missing_primary_role_fallback_to_member_ban` | Không có role thì fallback sang `Member.ban`. |

### 17.2. Classification tests

File:

```text
tests/test_evaluation_classification.py
```

| Test | Mục tiêu |
|---|---|
| `test_preliminary_classification_thresholds` | Xếp loại sơ bộ đúng ngưỡng. |
| `test_unexcused_absence_blocks_excellent` | Có vắng không phép không được Xuất sắc. |
| `test_attendance_under_80_blocks_good_or_above` | Chuyên cần dưới 80% tối đa Đạt. |
| `test_internal_warning_blocks_to_needs_improvement` | Cảnh cáo nội bộ tối đa Cần cải thiện. |
| `test_severe_violation_blocks_to_failed` | Vi phạm nghiêm trọng xếp Không đạt. |
| `test_multiple_blockers_apply_lowest_cap` | Nhiều blocker lấy trần thấp nhất. |

### 17.3. Evidence tests

File:

```text
tests/test_evaluation_evidence.py
```

| Test | Mục tiêu |
|---|---|
| `test_event_with_required_evidence_passes_when_evidence_exists` | Event có evidence hợp lệ được tính. |
| `test_event_with_required_evidence_fails_when_missing` | Thiếu evidence thì lỗi ở strict mode. |
| `test_event_without_required_evidence_passes` | Tiêu chí không yêu cầu evidence vẫn tính. |
| `test_approval_mode_requires_verified_evidence` | Mode approval chỉ nhận `VERIFIED`. |

### 17.4. Sync policy tests

File:

```text
tests/test_evaluation_sync_policy.py
```

| Test | Mục tiêu |
|---|---|
| `test_attendance_sync_is_idempotent` | Sync cùng meeting không tạo event trùng. |
| `test_absent_attendance_creates_penalty_event` | Vắng không phép tạo penalty event. |
| `test_excused_absence_does_not_create_unexcused_penalty` | Vắng có phép không tạo penalty vắng không phép. |
| `test_competition_sync_creates_bonus_event_once` | Competition bonus không cộng trùng. |

## 18. Dữ liệu mẫu kiểm thử

### 18.1. Thành viên một Ban

```text
Member A
Unit: BCNg
I = 27
II = 18
III_A = 25
III_B = 17
Total = 87
Classification = GOOD
```

### 18.2. Thành viên đa ban

```text
Member B
BCNg weight = 0.7, III_B unit score = 18/20
BTT weight = 0.3, III_B unit score = 16/20
III_B = 18 * 0.7 + 16 * 0.3 = 17.4
```

### 18.3. Blocker

```text
Member C
Total = 94
Preliminary = EXCELLENT
Blocker = UNEXCUSED_ABSENCE
Final = GOOD
```

```text
Member D
Total = 88
Preliminary = GOOD
Blocker = ATTENDANCE_UNDER_80
Final = PASSED
```

## 19. Definition of Done

Phase 2 hoàn thành khi:

- Có `EvaluationCalculatorService` tính được điểm theo member và cycle.
- Có `ClassificationPolicyService` áp dụng đúng ngưỡng xếp loại và điều kiện chặn.
- Có `EvidenceValidationService` kiểm tra được minh chứng theo mode.
- Có `EvaluationCriteriaSeedService` seed được tiêu chí lõi I, II, III-A.
- Có `EvaluationSyncService` tạo score events idempotent từ attendance/competition ở mức policy.
- Có unit test cho calculator, classification, evidence và sync policy.
- Service không phụ thuộc FastAPI router.
- API v1 legacy không bị thay đổi hành vi.
- Kết quả tính thử có thể ghi vào `member_evaluations` và `member_evaluation_breakdowns`.

## 20. Thứ tự triển khai đề xuất

1. Tạo `app/core/evaluation_constants.py`.
2. Tạo error classes cho evaluation service.
3. Tạo `EvaluationCriteriaSeedService` và seed tiêu chí lõi.
4. Tạo `EvidenceValidationService`.
5. Tạo `ClassificationPolicyService`.
6. Tạo `EvaluationCalculatorService.preview_member`.
7. Tạo `EvaluationCalculatorService.compute_member`.
8. Tạo `EvaluationCalculatorService.compute_cycle`.
9. Tạo `EvaluationSyncService` với idempotency policy.
10. Viết unit tests.
11. Chạy `pytest` và `ruff check .`.

## 21. Ghi chú chuyển tiếp sang Phase 3

Sau Phase 2, Phase 3 sẽ tạo router `/api/v2/evaluations` để expose các service:

- `POST /api/v2/evaluations/cycles/{cycle_id}/criteria/seed`
- `POST /api/v2/evaluations/cycles/{cycle_id}/score-events`
- `POST /api/v2/evaluations/cycles/{cycle_id}/compute`
- `GET /api/v2/evaluations/cycles/{cycle_id}/members`
- `GET /api/v2/evaluations/cycles/{cycle_id}/members/{member_id}`

Router chỉ nên làm:

- xác thực;
- phân quyền;
- validate request body;
- gọi service;
- map exception sang HTTP response.

Router không được chứa công thức tính điểm.
