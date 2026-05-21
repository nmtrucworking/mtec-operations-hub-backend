# Phase 5 Implementation Guide - Legacy Data Migration & Deprecation Plan

## 1. Mục tiêu Phase 5

Phase 5 tập trung chuyển đổi dữ liệu từ module Discipline legacy sang module `evaluations` v2 sau khi hệ thống đã có schema, service tính điểm, API v2 và workflow review/approval. Mục tiêu là bảo toàn dữ liệu cũ, chuyển dữ liệu có thể sử dụng thành score events/evidence/discipline cases, đối chiếu kết quả trước-sau và lập kế hoạch giảm phụ thuộc vào endpoint `/discipline-records`.

Phase này không xóa ngay bảng legacy. Dữ liệu cũ phải được giữ nguyên trong giai đoạn chuyển đổi để có khả năng rollback, đối chiếu và kiểm toán.

## 2. Đầu vào của Phase 5

Phase 5 giả định các phase trước đã hoàn thành:

- Phase 1: có schema lõi `evaluations`.
- Phase 2: có service tính điểm, classification, evidence validation và sync policy.
- Phase 3: có API v2 cho evaluation.
- Phase 4: có workflow đối soát, phê duyệt và khóa kỳ.

Dữ liệu legacy cần xử lý:

- `discipline_records`
- `attendances`
- `meetings`
- `competitions`
- `competition_results`
- audit logs liên quan discipline nếu cần đối chiếu

## 3. Phạm vi thực hiện

### 3.1. Trong phạm vi

| Hạng mục | Mục tiêu |
|---|---|
| Legacy data inventory | Thống kê dữ liệu legacy hiện có. |
| Data mapping | Map dữ liệu cũ sang mô hình evaluation v2. |
| Dry-run migration | Chạy thử migration không ghi hoặc ghi vào sandbox cycle. |
| Migration scripts | Tạo script chuyển đổi dữ liệu có kiểm soát. |
| Reconciliation | Đối chiếu kết quả cũ và mới. |
| Legacy API deprecation | Đưa `/discipline-records` vào trạng thái legacy/deprecated. |
| Rollback plan | Có phương án phục hồi nếu migration sai. |
| Tests | Test script migration, idempotency và dữ liệu sau chuyển đổi. |

### 3.2. Ngoài phạm vi

| Hạng mục | Lý do |
|---|---|
| Xóa bảng legacy | Chỉ thực hiện sau khi frontend và dữ liệu đã ổn định qua nhiều kỳ. |
| Tự động sửa mọi dữ liệu cũ thiếu minh chứng | Dữ liệu thiếu căn cứ cần gắn cờ, không tự suy diễn. |
| Thay toàn bộ frontend | Thuộc frontend migration plan. |
| Tái dựng kết quả lịch sử tuyệt đối chính xác | Legacy schema không đủ dữ liệu chi tiết, chỉ có thể migrate theo mức độ tin cậy. |
| Chuẩn hóa toàn bộ audit lịch sử | Có thể bổ sung sau nếu cần kiểm toán sâu. |

## 4. Nguyên tắc migration

1. Không xóa hoặc sửa destructive dữ liệu legacy trong lần migration đầu.
2. Migration phải idempotent: chạy nhiều lần không tạo dữ liệu trùng.
3. Mọi dữ liệu chuyển đổi phải có `source_type` và `source_id`.
4. Mọi record sinh từ legacy phải có `metadata_json` ghi rõ nguồn legacy.
5. Không dùng `discipline_records.kpi` làm điểm cuối cùng của quy chế mới nếu không có breakdown tiêu chí.
6. Legacy data không đủ minh chứng phải được gắn cờ `LEGACY_IMPORT_UNVERIFIED` hoặc evidence trạng thái `PENDING`.
7. Kết quả migration phải có báo cáo số lượng: created, skipped, failed, warnings.
8. Migration phải hỗ trợ `dry_run` trước khi ghi DB.
9. Không migrate vào cycle đã `LOCKED`.
10. Không thay đổi API v1 trong bước đầu; chỉ bổ sung cảnh báo deprecation nếu cần.

## 5. Legacy data inventory

Trước khi migrate, cần tạo báo cáo inventory.

File script đề xuất:

```text
scripts/evaluation_legacy_inventory.py
```

Thông tin cần thống kê:

| Nguồn | Chỉ số cần lấy |
|---|---|
| `discipline_records` | Tổng số record, số record có `member_id`, số record không có `member_id`, phân bố `discipline_level`, min/max/avg `absents`, min/max/avg `kpi`. |
| `attendances` | Tổng số attendance, phân bố status `Present/Absent/Excused`, số meeting, số member. |
| `meetings` | Tổng số meeting, phân bố `meeting_type`, status, khoảng thời gian. |
| `competitions` | Tổng số competition, status, scale. |
| `competition_results` | Tổng result, số đã `is_synced=True`, tổng `bonus_kpi`, phân bố achievement. |
| `members` | Tổng active members, phân bố Ban/Tổ. |

Output đề xuất:

```text
artifacts/evaluation_legacy_inventory_<timestamp>.json
artifacts/evaluation_legacy_inventory_<timestamp>.md
```

## 6. Mapping dữ liệu legacy sang evaluation v2

## 6.1. `discipline_records.absents`

Legacy field:

```text
discipline_records.absents
```

Mapping đề xuất:

| Legacy value | Evaluation v2 target |
|---|---|
| `absents > 0` | Tạo `evaluation_score_events` cho tiêu chí `I.1` hoặc `I.2` tùy chính sách. |
| Không biết từng buổi vắng | Tạo event tổng hợp `LEGACY_IMPORT`. |
| Không có minh chứng | Tạo evidence `LEGACY_SUMMARY` hoặc metadata `unverified=true`. |

Event đề xuất:

```text
criterion_code = I.1 hoặc I.2
component = I
event_type = LEGACY_IMPORT
source_type = LEGACY_DISCIPLINE_RECORD
source_id = discipline_record.id
raw_value = absents
score_delta = computed penalty hoặc 0 nếu chỉ lưu snapshot
metadata_json = {"legacyField": "absents", "confidence": "LOW|MEDIUM"}
```

Khuyến nghị:

- Nếu có dữ liệu attendance chi tiết cùng kỳ, ưu tiên migrate từ `attendances` thay vì `discipline_records.absents`.
- `discipline_records.absents` chỉ nên dùng để đối chiếu hoặc tạo event tổng hợp khi không có attendance.

## 6.2. `discipline_records.discipline_level`

Legacy field:

```text
discipline_records.discipline_level
```

Mapping đề xuất sang `discipline_cases`:

| Legacy level | Case type | Severity | Blocker |
|---|---|---|---|
| `Không`, `Khong`, empty | Không tạo case | N/A | N/A |
| `Nhắc nhở` | `REMINDER` | `LOW` | Có thể không blocker |
| `Cảnh cáo Lần 1`, `Cảnh cáo`, `Canh cao` | `WARNING` | `MEDIUM` | `INTERNAL_WARNING` |
| `Đình chỉ` | `SUSPENSION` | `HIGH` | `SEVERE_VIOLATION` hoặc custom blocker |
| `Khai trừ`, `Xem xét khai trừ` | `EXPULSION_REVIEW` | `CRITICAL` | `SEVERE_VIOLATION` |
| Giá trị khác | `LEGACY_OTHER` | `MEDIUM` | cần review thủ công |

Case metadata:

```json
{
  "source": "discipline_records",
  "legacyRecordId": "...",
  "legacyDisciplineLevel": "...",
  "migrationConfidence": "MEDIUM",
  "requiresManualReview": false
}
```

## 6.3. `discipline_records.kpi`

Legacy field:

```text
discipline_records.kpi
```

Không nên map trực tiếp sang `total_score` hoặc điểm III vì KPI cũ không có breakdown theo cấu phần. Mapping an toàn:

| Trường hợp | Cách xử lý |
|---|---|
| Có `kpi` nhưng không có nguồn chi tiết | Lưu snapshot vào `metadata_json` của `member_evaluations` hoặc tạo event `LEGACY_KPI_SNAPSHOT` không ảnh hưởng điểm. |
| KPI đến từ `competition_results` có nguồn | Migrate từ `competition_results` thành score event bonus theo tiêu chí phù hợp. |
| KPI bất thường > 100 | Gắn warning để review thủ công. |
| KPI = 0 hoặc null | Không dùng làm điểm. |

Event snapshot nếu cần:

```text
event_type = LEGACY_IMPORT
source_type = LEGACY_DISCIPLINE_KPI
source_id = discipline_record.id
criterion_code = LEGACY.KPI_SNAPSHOT hoặc không tạo nếu chưa có criterion legacy
score_delta = 0
metadata_json = {"legacyKpi": 120.0, "affectsScore": false}
```

Khuyến nghị: không đưa `LEGACY.KPI_SNAPSHOT` vào bộ tiêu chí chính thức. Chỉ dùng metadata hoặc report reconciliation.

## 6.4. `attendances`

Legacy/source tables:

```text
meetings
attendances
```

Mapping sang score events:

| Attendance status | Target |
|---|---|
| `Present` | Có thể tạo base/ratio input cho `I.1`. |
| `Absent` | Tạo penalty/input cho `I.1` và blocker `UNEXCUSED_ABSENCE` nếu policy yêu cầu. |
| `Excused` | Ghi nhận hợp lệ cho `I.2`, không tạo blocker vắng không phép. |

Đề xuất Phase 5:

- Không tạo event cho từng `Present` nếu calculator có thể tính attendance rate trực tiếp từ attendance source.
- Tạo score event cho `Absent` và các trường hợp cần audit rõ.
- Với các kỳ lịch sử cần đóng gói, có thể tạo aggregated event theo member/cycle:

```text
source_type = ATTENDANCE_AGGREGATE
source_id = cycle_id + member_id
raw_value = attendance_rate
score_delta = attendance_rate * 15
criterion_code = I.1
event_type = BASE
```

## 6.5. `competition_results`

Legacy/source tables:

```text
competitions
competition_results
```

Mapping sang score events:

| Legacy field | Evaluation target |
|---|---|
| `achievement` | `note` hoặc `metadata_json.achievement`. |
| `bonus_kpi` | `score_delta` nếu được BCN xác nhận quy đổi. |
| `is_synced` | Chỉ dùng để nhận biết legacy đã từng sync, không dùng làm idempotency chính của v2. |
| `competition_id` | `source_id`. |

Event đề xuất:

```text
criterion_code = III-A.5 hoặc III-B.<unit>.innovation/contribution criterion
component = III_A hoặc III_B
event_type = BONUS
source_type = COMPETITION_RESULT
source_id = competition_result.id
score_delta = mapped bonus score
metadata_json = {"legacyBonusKpi": ..., "achievement": ..., "competitionId": ...}
```

Khuyến nghị:

- Nếu chưa có tiêu chí III-B chi tiết, map tạm vào `III-A.5` với cap 3 điểm.
- Nếu `bonus_kpi` vượt trần tiêu chí, calculator phải cap theo tiêu chí.
- Không dùng `competition_results.is_synced` để bỏ qua migration v2; dùng unique source key của v2.

## 7. Migration strategy

## 7.1. Chọn migration mode

| Mode | Mục đích | Ghi DB? |
|---|---|---:|
| `inventory` | Chỉ thống kê dữ liệu. | Không |
| `dry_run` | Simulate mapping, xuất report. | Không |
| `sandbox` | Ghi vào cycle thử nghiệm. | Có |
| `production` | Ghi vào cycle chính thức. | Có |

CLI đề xuất:

```bash
python scripts/migrate_legacy_discipline_to_evaluations.py --mode inventory
python scripts/migrate_legacy_discipline_to_evaluations.py --mode dry_run --cycle-id <cycle_id>
python scripts/migrate_legacy_discipline_to_evaluations.py --mode sandbox --cycle-id <sandbox_cycle_id>
python scripts/migrate_legacy_discipline_to_evaluations.py --mode production --cycle-id <cycle_id>
```

## 7.2. Batch processing

Với dữ liệu lớn, migration nên xử lý batch:

```text
--batch-size 100
--member-id <optional>
--from-date <optional>
--to-date <optional>
```

Batch summary:

```json
{
  "mode": "dry_run",
  "cycleId": "...",
  "processed": 100,
  "createdScoreEvents": 0,
  "createdDisciplineCases": 0,
  "createdEvidence": 0,
  "skipped": 12,
  "failed": 1,
  "warnings": []
}
```

## 7.3. Idempotency keys

Score event unique identity:

```text
cycle_id
member_id
criterion_code
source_type
source_id
event_type
```

Discipline case unique identity:

```text
case_code = LEGACY-DR-{discipline_record.id}
```

Evidence unique identity:

```text
source_type + source_id + evidence_type + title
```

Nếu record đã tồn tại:

- không tạo duplicate;
- increment `skipped`;
- nếu payload khác, ghi warning `CONFLICTING_LEGACY_MAPPING`.

## 8. Script migration đề xuất

File:

```text
scripts/migrate_legacy_discipline_to_evaluations.py
```

Các thành phần chính:

```python
def parse_args():
    ...


def load_cycle(db, cycle_id):
    ...


def ensure_cycle_mutable(cycle):
    ...


def build_inventory(db) -> dict:
    ...


def migrate_discipline_records(db, cycle_id, *, dry_run: bool) -> dict:
    ...


def migrate_attendance_records(db, cycle_id, *, dry_run: bool) -> dict:
    ...


def migrate_competition_results(db, cycle_id, *, dry_run: bool) -> dict:
    ...


def write_report(summary: dict, output_path: str) -> None:
    ...
```

Transaction policy:

| Mode | Transaction |
|---|---|
| `dry_run` | Rollback cuối script hoặc không add vào session. |
| `sandbox` | Commit theo batch. |
| `production` | Commit theo batch, lưu report đầy đủ. |

## 9. Reconciliation plan

Sau migration cần đối chiếu dữ liệu cũ và mới.

## 9.1. Đối chiếu số lượng

| Check | Công thức |
|---|---|
| Discipline cases | Số `discipline_records.discipline_level != Không/Khong` ≈ số `discipline_cases` source legacy. |
| Absence source | Số member có `absents > 0` ≈ số member có event/case tương ứng. |
| Competition source | Số `competition_results.bonus_kpi > 0` ≈ số score events `source_type=COMPETITION_RESULT`. |
| Evidence placeholder | Số migrated event thiếu minh chứng thực tế = số evidence placeholder hoặc warning. |

## 9.2. Đối chiếu điểm

Không kỳ vọng điểm v2 bằng KPI cũ. Cần phân loại chênh lệch:

| Loại chênh lệch | Ý nghĩa |
|---|---|
| `EXPECTED_MODEL_CHANGE` | Khác do công thức mới 100 điểm. |
| `MISSING_EVIDENCE` | Khác do dữ liệu cũ thiếu minh chứng. |
| `MISSING_CRITERIA_MAPPING` | Chưa có mapping tiêu chí III-B chi tiết. |
| `LEGACY_DATA_INCONSISTENT` | Dữ liệu cũ mâu thuẫn, ví dụ `absents=0` nhưng discipline level cảnh cáo. |
| `NEEDS_MANUAL_REVIEW` | Cần người phụ trách xác minh. |

## 9.3. Reconciliation report

Output đề xuất:

```text
artifacts/evaluation_migration_reconciliation_<timestamp>.md
artifacts/evaluation_migration_reconciliation_<timestamp>.json
```

Report cần có:

- tổng số record legacy;
- tổng số migrated entities;
- danh sách warning theo loại;
- danh sách member cần review thủ công;
- bảng phân bố classification sau compute;
- so sánh legacy `discipline_level` với v2 blockers;
- so sánh legacy `kpi` với v2 `total_score` chỉ để tham khảo.

## 10. Manual review queue

Không nên ép mọi dữ liệu legacy vào điểm mới nếu thiếu căn cứ. Các trường hợp sau cần đưa vào hàng đợi review thủ công:

| Điều kiện | Lý do |
|---|---|
| `discipline_level` không thuộc mapping chuẩn | Không xác định được case type/severity. |
| `absents > 0` nhưng không có attendance chi tiết | Không xác minh được buổi vắng. |
| `kpi > 100` hoặc `kpi < 0` | KPI legacy bất thường. |
| `member_id` null và không match được `mssv` | Không xác định được thành viên. |
| `competition_results.bonus_kpi` quá lớn | Có thể vượt trần tiêu chí mới. |
| Attendance có member đã inactive/deleted | Cần xác định có đưa vào kỳ đánh giá không. |

Có thể tạo output:

```text
artifacts/evaluation_manual_review_queue_<timestamp>.csv
```

Columns:

```text
source_type,source_id,member_id,mssv,name,issue_code,issue_detail,suggested_action
```

## 11. API deprecation plan

Endpoint legacy:

```text
/api/v1/discipline-records
```

## 11.1. Giai đoạn deprecation

| Giai đoạn | Hành động |
|---|---|
| Stage 1 | Giữ nguyên API v1, bổ sung tài liệu cảnh báo legacy. |
| Stage 2 | Thêm response header `X-MTEC-Deprecated: true` cho endpoint v1. |
| Stage 3 | Frontend chuyển sang API v2; v1 chỉ read-only. |
| Stage 4 | Chặn create/update v1, yêu cầu dùng evaluation v2. |
| Stage 5 | Xóa hoặc archive v1 sau ít nhất 2-3 kỳ đánh giá ổn định. |

## 11.2. Read-only legacy mode

Khi chuyển v1 sang read-only:

Không cho phép:

- `POST /discipline-records`
- `PATCH /discipline-records/{record_id}`
- `POST /discipline-records/sync-attendance/{meeting_id}`
- `POST /discipline-records/sync-competition-kpi/{competition_id}`

Cho phép tạm thời:

- `GET /discipline-records`
- `GET /discipline-records/stats`

Response lỗi đề xuất:

```json
{
  "code": "DISCIPLINE_LEGACY_READ_ONLY",
  "message": "Discipline legacy module is read-only. Use /api/v2/evaluations instead."
}
```

## 12. Frontend migration contract

Frontend nên chuyển dần từ legacy fields sang v2 fields.

| Legacy field | V2 replacement |
|---|---|
| `absents` | `componentIScore`, attendance breakdown, blockers. |
| `kpi` | `totalScore`, component scores. |
| `disciplineLevel` | `disciplineCases`, blockers, final classification. |
| `committee` | `memberCycleRoles.unitCode`. |
| `note` | score event note, evidence description, appeal resolution note. |

Legacy screen có thể chuyển thành:

| Màn hình cũ | Màn hình mới |
|---|---|
| Discipline list | Evaluation cycle member results. |
| Discipline stats | Evaluation cycle summary. |
| Edit discipline record | Create score event / resolve appeal / create discipline case. |
| Sync attendance | Sync attendance score events. |
| Sync competition KPI | Sync competition score events. |

## 13. Data validation rules trước production migration

Trước khi chạy `--mode production`, phải kiểm tra:

- [ ] Có cycle target và cycle chưa `LOCKED`.
- [ ] Criteria I, II, III-A đã seed.
- [ ] Nếu migrate competition sang III-B, criteria III-B tương ứng đã tồn tại.
- [ ] Tất cả active members có thể match bằng `member_id` hoặc `mssv`.
- [ ] Đã chạy `inventory` và lưu report.
- [ ] Đã chạy `dry_run` và không có blocking errors.
- [ ] Đã chạy `sandbox` trên cycle thử nghiệm.
- [ ] Đã compute sandbox cycle và review reconciliation report.
- [ ] Có backup database trước migration.
- [ ] Có kế hoạch rollback.

## 14. Backup và rollback

## 14.1. Backup

Trước production migration:

SQLite:

```bash
copy mtec_ops.db backups/mtec_ops_before_eval_migration_<timestamp>.db
```

PostgreSQL:

```bash
pg_dump "$DATABASE_URL" > backups/mtec_ops_before_eval_migration_<timestamp>.sql
```

## 14.2. Rollback soft

Vì migration dữ liệu dùng source keys, có thể rollback bằng cách void hoặc xóa các record có metadata source migration.

Soft rollback đề xuất:

- set `is_void=True` cho score events tạo bởi migration;
- set `status=CANCELLED` cho discipline cases tạo bởi migration;
- không xóa evidence, chỉ mark `REJECTED` hoặc metadata `rolledBack=true` nếu cần.

## 14.3. Rollback hard

Chỉ dùng nếu migration nghiêm trọng:

- restore database backup;
- hoặc chạy script xóa theo `migration_batch_id` nếu Phase 5 bổ sung trường này trong `metadata_json`.

Khuyến nghị: mọi migrated entity nên có:

```json
{
  "migrationBatchId": "2026-05-21T...",
  "sourceModule": "discipline_legacy"
}
```

## 15. Migration batch metadata

Mỗi lần chạy migration phải sinh `migration_batch_id`.

Format đề xuất:

```text
eval-legacy-YYYYMMDD-HHMMSS
```

Metadata chung:

```json
{
  "migrationBatchId": "eval-legacy-20260521-183000",
  "sourceModule": "discipline_legacy",
  "sourceTable": "discipline_records",
  "sourceId": "...",
  "migrationMode": "production",
  "migrationVersion": "phase5-v1"
}
```

## 16. Audit log requirements

| Action | Khi ghi |
|---|---|
| `LEGACY_INVENTORY_DISCIPLINE` | Khi chạy inventory. |
| `LEGACY_MIGRATION_DRY_RUN` | Khi chạy dry-run. |
| `LEGACY_MIGRATION_START` | Trước khi chạy production migration. |
| `LEGACY_MIGRATION_CREATE_SCORE_EVENT` | Khi tạo score event từ legacy. |
| `LEGACY_MIGRATION_CREATE_DISCIPLINE_CASE` | Khi tạo discipline case từ legacy. |
| `LEGACY_MIGRATION_CREATE_EVIDENCE` | Khi tạo evidence placeholder. |
| `LEGACY_MIGRATION_COMPLETE` | Khi migration hoàn tất. |
| `LEGACY_MIGRATION_ROLLBACK` | Khi rollback. |
| `MARK_DISCIPLINE_LEGACY_READ_ONLY` | Khi chuyển v1 sang read-only. |

Không nhất thiết ghi audit log cho từng record nếu dữ liệu nhiều; có thể ghi batch audit và lưu report file path trong snapshot.

## 17. Test bắt buộc Phase 5

File đề xuất:

```text
tests/test_evaluation_legacy_migration.py
```

## 17.1. Inventory tests

| Test | Mục tiêu |
|---|---|
| `test_inventory_counts_discipline_records` | Inventory đếm đúng discipline records. |
| `test_inventory_counts_attendance_statuses` | Inventory phân bố attendance status đúng. |
| `test_inventory_detects_unmatched_members` | Phát hiện record không match member. |

## 17.2. Mapping tests

| Test | Mục tiêu |
|---|---|
| `test_map_discipline_warning_to_discipline_case` | Cảnh cáo legacy tạo case đúng. |
| `test_map_no_discipline_level_skips_case` | Không/Khong không tạo case. |
| `test_map_absents_to_legacy_score_event` | Absents tạo score event tổng hợp nếu cần. |
| `test_map_competition_result_to_bonus_event` | Competition bonus tạo event đúng. |
| `test_kpi_is_snapshot_not_total_score` | KPI không bị gán trực tiếp vào total score. |

## 17.3. Idempotency tests

| Test | Mục tiêu |
|---|---|
| `test_migration_is_idempotent_for_score_events` | Chạy 2 lần không tạo event trùng. |
| `test_migration_is_idempotent_for_discipline_cases` | Không tạo case trùng. |
| `test_conflicting_existing_event_is_reported` | Existing event khác payload thì warning. |

## 17.4. Dry-run and rollback tests

| Test | Mục tiêu |
|---|---|
| `test_dry_run_does_not_commit_records` | Dry-run không ghi DB. |
| `test_soft_rollback_voids_migrated_events` | Soft rollback void event migration. |
| `test_rollback_uses_migration_batch_id` | Rollback chỉ ảnh hưởng batch được chọn. |

## 17.5. Legacy API deprecation tests

| Test | Mục tiêu |
|---|---|
| `test_legacy_get_still_works_during_stage_1` | API read legacy vẫn hoạt động. |
| `test_legacy_mutation_rejected_in_read_only_mode` | Read-only mode chặn POST/PATCH/sync. |
| `test_legacy_response_contains_deprecation_header` | Response có header cảnh báo khi bật. |

## 18. Manual QA checklist

- [ ] Chạy inventory trên DB dev.
- [ ] Review inventory report.
- [ ] Tạo sandbox evaluation cycle.
- [ ] Seed criteria vào sandbox.
- [ ] Chạy dry-run migration.
- [ ] Review dry-run warnings.
- [ ] Chạy sandbox migration.
- [ ] Compute sandbox cycle.
- [ ] Review reconciliation report.
- [ ] Kiểm tra member có discipline legacy đã được map case/blocker đúng.
- [ ] Kiểm tra competition bonus không vượt cap điểm.
- [ ] Kiểm tra dữ liệu thiếu minh chứng nằm trong manual review queue.
- [ ] Backup DB production.
- [ ] Chạy production migration.
- [ ] Compute target cycle.
- [ ] Xuất reconciliation report production.
- [ ] Chuyển frontend test sang endpoint v2.
- [ ] Bật deprecation header cho legacy API.
- [ ] Sau khi ổn định, bật read-only mode cho legacy mutations.

## 19. Feature flags đề xuất

Nên dùng biến môi trường để kiểm soát deprecation:

```text
DISCIPLINE_LEGACY_DEPRECATION_HEADER=false
DISCIPLINE_LEGACY_READ_ONLY=false
EVALUATION_LEGACY_MIGRATION_ENABLED=false
```

Ý nghĩa:

| Flag | Mục đích |
|---|---|
| `DISCIPLINE_LEGACY_DEPRECATION_HEADER` | Thêm header cảnh báo ở API v1. |
| `DISCIPLINE_LEGACY_READ_ONLY` | Chặn mutation trên API v1. |
| `EVALUATION_LEGACY_MIGRATION_ENABLED` | Cho phép chạy script migration production. |

## 20. Production rollout plan

| Bước | Hành động | Điều kiện qua bước |
|---:|---|---|
| 1 | Inventory production | Report không có lỗi blocking. |
| 2 | Dry-run production | Warning nằm trong ngưỡng chấp nhận. |
| 3 | Sandbox migration | Compute được kết quả và reconciliation hợp lệ. |
| 4 | Backup production DB | Backup được xác nhận. |
| 5 | Production migration | Script hoàn tất, không có failed blocking. |
| 6 | Compute target cycle | Kết quả tạo đủ cho target members. |
| 7 | Manual review | Các case cần review được xử lý hoặc ghi nhận. |
| 8 | Frontend switch | Frontend đọc từ v2 cho màn hình evaluation. |
| 9 | Deprecation header | Legacy API trả header cảnh báo. |
| 10 | Read-only legacy | Chặn mutation legacy. |
| 11 | Archive legacy | Chỉ sau nhiều kỳ ổn định. |

## 21. Definition of Done

Phase 5 hoàn thành khi:

- Có script inventory cho dữ liệu legacy.
- Có script migration hỗ trợ `dry_run`, `sandbox`, `production`.
- Migration idempotent, chạy lại không tạo duplicate.
- `discipline_records.discipline_level` được map sang `discipline_cases` khi hợp lệ.
- `attendances` được map hoặc dùng làm nguồn tính chuyên cần theo policy v2.
- `competition_results` được map thành score events theo tiêu chí phù hợp.
- `discipline_records.kpi` chỉ dùng làm snapshot/reconciliation, không gán trực tiếp thành điểm mới.
- Có reconciliation report sau migration.
- Có manual review queue cho dữ liệu thiếu minh chứng hoặc mâu thuẫn.
- Có backup và rollback plan đã kiểm thử.
- Có test cho mapping, idempotency, dry-run và rollback.
- Legacy API có kế hoạch deprecation rõ ràng.
- API v1 không bị xóa đột ngột và frontend có đường chuyển sang v2.

## 22. Thứ tự triển khai đề xuất

1. Tạo script inventory.
2. Tạo mapper functions cho discipline level, absence, competition bonus.
3. Tạo migration script với `dry_run` trước.
4. Thêm `migration_batch_id` vào metadata các record sinh ra.
5. Viết test cho mapping và idempotency.
6. Chạy inventory trên dev DB.
7. Chạy dry-run trên dev DB.
8. Chạy sandbox migration.
9. Tạo reconciliation report.
10. Hoàn thiện rollback soft.
11. Thêm feature flags legacy deprecation.
12. Bật deprecation header ở môi trường dev/staging.
13. Sau khi frontend sẵn sàng, bật read-only legacy mode.
14. Lập biên bản kết thúc migration.

## 23. Ghi chú chuyển tiếp sau Phase 5

Sau Phase 5, module `evaluations` có thể trở thành nguồn dữ liệu chính thức cho đánh giá thành viên. Các việc nên làm tiếp theo:

- Phase 6: reporting/export PDF/Excel và dashboard tổng hợp.
- Phase 7: frontend migration hoàn chỉnh.
- Phase 8: hardening RBAC theo unit-level permission.
- Phase 9: archive hoặc xóa legacy module sau khi có đủ dữ liệu ổn định.
