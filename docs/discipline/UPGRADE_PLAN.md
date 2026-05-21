# Discipline / Evaluation Upgrade Plan

## 1. Mục đích tài liệu

Tài liệu này tổng kết tình trạng module Discipline hiện tại của `mtec-operations-hub-backend` và xác định kế hoạch nâng cấp để đáp ứng Quy chế đánh giá và xếp loại thành viên MTEC theo hướng định lượng, có minh chứng, có đối soát và có khả năng mở rộng cho thành viên đa ban.

Tài liệu này là đầu vào cho các bước triển khai tiếp theo: thiết kế schema, viết migration, tách service tính điểm, xây API v2, bổ sung test và dần thay thế module Discipline legacy.

## 2. Căn cứ nghiệp vụ

Nguồn nghiệp vụ chính:

- Quy chế QC-MTEC-03/2026 - Dự thảo Quy chế đánh giá thành viên MTEC.
- Bảng tiêu chí đánh giá thành viên chi tiết.
- Source hiện tại của backend FastAPI trong repository `nmtrucworking/mtec-operations-hub-backend`.

Các yêu cầu trọng tâm từ quy chế:

| Nhóm yêu cầu | Nội dung cần hỗ trợ |
|---|---|
| Thang điểm | Tổng điểm 100, gồm I = 30, II = 20, III = 50. |
| Cấu phần I | Kỷ luật và chuyên cần, gồm tham gia, xin phép, đúng giờ, nghĩa vụ hành chính. |
| Cấu phần II | Thái độ và ý thức tổ chức. |
| Cấu phần III | Hiệu suất chuyên môn, gồm III-A dùng chung 30 và III-B đặc thù Ban/Tổ 20. |
| Minh chứng | Mọi điểm cộng/trừ và vi phạm cần có minh chứng xác thực. |
| Đối soát | Thành viên có quyền kiểm tra và yêu cầu chỉnh sửa dữ liệu đánh giá. |
| Đa ban | Thành viên đa ban cần tính III-B theo trọng số tham gia từng Ban/Tổ. |
| Xếp loại | Xuất sắc, Tốt, Đạt, Cần cải thiện, Không đạt. |
| Điều kiện chặn | Điểm cao vẫn bị hạ xếp loại nếu có vắng không phép, chuyên cần dưới chuẩn, cảnh cáo hoặc vi phạm nghiêm trọng. |

## 3. Tình trạng source hiện tại

### 3.1. Nền tảng backend

Backend hiện tại đã có các thành phần có thể tái sử dụng:

- FastAPI router structure.
- SQLAlchemy ORM.
- Alembic migration.
- RBAC theo role.
- Audit log.
- Module members, meetings, attendances, competitions.
- API v1 đang vận hành.
- API v2 đã có khung nhưng mới mount auth.

Các thành phần này đủ làm nền để nâng cấp, không cần thay toàn bộ source.

### 3.2. Module Discipline hiện tại

Module hiện tại xoay quanh bảng `discipline_records` với các trường chính:

- `member_id`
- `mssv`
- `name`
- `committee`
- `absents`
- `kpi`
- `discipline_level`
- `note`
- `updated_by`
- `updated_at`

Router hiện tại có các chức năng:

- Liệt kê discipline records.
- Thống kê số record, số cảnh cáo, KPI trung bình.
- Tạo record.
- Cập nhật record.
- Đồng bộ vắng mặt từ attendance.
- Đồng bộ KPI thưởng từ competition result.

### 3.3. Khoảng cách so với quy chế

| Vấn đề | Mức độ | Nhận định |
|---|---:|---|
| Không có kỳ đánh giá | Cao | Không thể đánh giá theo tháng/quý/kỳ hoạt động. |
| Không có bảng tiêu chí | Cao | Không lưu được I.1, I.2, II.1, III-A.1, III-B theo Ban/Tổ. |
| Không có minh chứng có cấu trúc | Cao | `note` không đủ thay thế evidence có khả năng truy xuất. |
| Không có breakdown điểm | Cao | Không thể giải trình tổng điểm 100. |
| Không hỗ trợ đa ban | Cao | Chỉ có một `committee`, không có trọng số tham gia. |
| Không có quy trình đối soát | Cao | Chưa có appeal/review flow. |
| Logic KPI chưa đúng quy chế | Cao | Điểm thưởng đang cộng trực tiếp vào KPI, không bị chặn theo cấu phần/tiêu chí. |
| Logic đồng bộ attendance có nguy cơ cộng lặp | Trung bình | Gọi sync nhiều lần cho cùng meeting có thể tăng `absents` nhiều lần. |
| Router chứa nhiều business logic | Trung bình | Khó test, khó bảo trì, khó mở rộng. |
| Migration/model có nguy cơ lệch | Trung bình | Cần rà soát lại `meetings.minutes_url` và schema thực tế. |

## 4. Quyết định kiến trúc

### 4.1. Định hướng chính

Không mở rộng trực tiếp `discipline_records` để gánh toàn bộ quy chế mới. Thay vào đó, xây module mới theo hướng `Evaluation` hoặc `Member Evaluation` trong `/api/v2`.

`discipline_records` nên được giữ tạm như legacy summary để tránh phá API v1 và frontend hiện tại.

### 4.2. Tên miền nghiệp vụ đề xuất

Tên module mới nên là:

```text
evaluations
```

Lý do:

- Quy chế không chỉ là kỷ luật, mà là đánh giá thành viên toàn diện.
- Discipline chỉ nên là một phần của cấu phần I và hồ sơ vi phạm.
- Tên `evaluations` phù hợp với đánh giá định kỳ, tính điểm, đối soát và phê duyệt.

### 4.3. Nguyên tắc triển khai

- Giữ API v1 hiện tại trong ngắn hạn.
- Xây API v2 cho module đánh giá mới.
- Không hard-code tiêu chí trong router.
- Tách calculator/service khỏi router.
- Mỗi điểm cộng/trừ phải gắn với tiêu chí, kỳ đánh giá, người ghi nhận và minh chứng.
- Tổng điểm và xếp loại phải tính lại được từ dữ liệu nguồn.
- Kết quả đã phê duyệt/khóa không được sửa trực tiếp, chỉ điều chỉnh bằng event hoặc appeal được phê duyệt.

## 5. Mô hình dữ liệu đề xuất

| Bảng | Mục đích |
|---|---|
| `evaluation_cycles` | Lưu kỳ đánh giá: tháng/quý/đột xuất, thời gian, trạng thái. |
| `evaluation_criteria` | Lưu bộ tiêu chí, mã tiêu chí, điểm tối đa, cấu phần, đơn vị áp dụng. |
| `evaluation_score_events` | Lưu điểm cộng/trừ/dữ liệu đầu vào theo từng tiêu chí. |
| `evaluation_evidence` | Lưu minh chứng: link, file, task, biên bản, log, timestamp. |
| `member_evaluations` | Lưu kết quả tổng hợp cuối kỳ của từng thành viên. |
| `member_evaluation_breakdowns` | Lưu điểm theo cấu phần và tiêu chí để giải trình. |
| `member_cycle_roles` | Lưu Ban chính, Ban phụ, vai trò và trọng số tham gia trong kỳ. |
| `evaluation_appeals` | Lưu yêu cầu đối soát/khiếu nại và kết quả xử lý. |
| `discipline_cases` | Lưu hồ sơ nhắc nhở, cảnh cáo, đình chỉ, khai trừ. |

## 6. Luồng nghiệp vụ mục tiêu

### 6.1. Luồng đánh giá định kỳ

1. Ban Vận hành tạo kỳ đánh giá.
2. Hệ thống nạp dữ liệu nền: attendance, request, deadline, nghĩa vụ hành chính.
3. Trưởng ban hoặc người phụ trách ghi nhận điểm chuyên môn, thái độ và minh chứng.
4. Hệ thống tính điểm theo cấu phần và tiêu chí.
5. Thành viên xem kết quả sơ bộ và gửi đối soát nếu cần.
6. Ban Vận hành xử lý đối soát.
7. Ban Chủ nhiệm phê duyệt kết quả.
8. Hệ thống khóa kỳ đánh giá và xuất báo cáo.

### 6.2. Luồng tính điểm

```text
total_score = component_i + component_ii + component_iii_a + component_iii_b
```

Ràng buộc:

```text
0 <= component_i <= 30
0 <= component_ii <= 20
0 <= component_iii_a <= 30
0 <= component_iii_b <= 20
0 <= total_score <= 100
```

### 6.3. Luồng tính III-B đa ban

```text
iii_b_score = sum(unit_iii_b_score_20 * participation_weight)
```

Điều kiện:

- Tổng trọng số tham gia phải bằng 100%.
- Mỗi nhiệm vụ chỉ được tính một lần.
- Nhiệm vụ liên ban phải phân bổ theo vai trò thực tế.
- Không dùng điểm cao ở Ban/Tổ này để che vi phạm nghiêm trọng ở Ban/Tổ khác.

### 6.4. Luồng xếp loại

Xếp loại sơ bộ theo tổng điểm:

| Tổng điểm | Xếp loại |
|---:|---|
| 90 - 100 | Xuất sắc |
| 80 - dưới 90 | Tốt |
| 65 - dưới 80 | Đạt |
| 50 - dưới 65 | Cần cải thiện |
| Dưới 50 | Không đạt |

Sau đó áp dụng điều kiện chặn:

| Điều kiện | Trần xếp loại |
|---|---|
| Có vắng không phép | Không được Xuất sắc |
| Chuyên cần dưới 80% | Không được Tốt trở lên |
| Trễ hạn/thiếu trách nhiệm lặp lại | Tối đa Đạt |
| Có cảnh cáo nội bộ | Tối đa Cần cải thiện |
| Vi phạm nghiêm trọng | Không đạt |

## 7. API v2 đề xuất

| Method | Endpoint | Mục đích |
|---|---|---|
| POST | `/api/v2/evaluations/cycles` | Tạo kỳ đánh giá. |
| GET | `/api/v2/evaluations/cycles` | Danh sách kỳ đánh giá. |
| GET | `/api/v2/evaluations/cycles/{cycle_id}` | Chi tiết kỳ đánh giá. |
| POST | `/api/v2/evaluations/cycles/{cycle_id}/criteria/import` | Import hoặc seed tiêu chí. |
| POST | `/api/v2/evaluations/cycles/{cycle_id}/score-events` | Ghi nhận điểm cộng/trừ. |
| POST | `/api/v2/evaluations/cycles/{cycle_id}/evidence` | Gắn minh chứng. |
| POST | `/api/v2/evaluations/cycles/{cycle_id}/member-roles` | Ghi nhận Ban chính/Ban phụ/trọng số. |
| POST | `/api/v2/evaluations/cycles/{cycle_id}/compute` | Tính hoặc tái tính điểm. |
| GET | `/api/v2/evaluations/cycles/{cycle_id}/members` | Xem danh sách kết quả. |
| GET | `/api/v2/evaluations/cycles/{cycle_id}/members/{member_id}` | Xem chi tiết điểm một thành viên. |
| POST | `/api/v2/evaluations/cycles/{cycle_id}/appeals` | Thành viên gửi đối soát. |
| PATCH | `/api/v2/evaluations/appeals/{appeal_id}` | Xử lý đối soát. |
| POST | `/api/v2/evaluations/cycles/{cycle_id}/approve` | BCN phê duyệt kết quả. |
| POST | `/api/v2/evaluations/cycles/{cycle_id}/lock` | Khóa kỳ đánh giá. |

## 8. Phân quyền mục tiêu

| Vai trò | Quyền chính |
|---|---|
| `bcn` | Phê duyệt, khóa kỳ, override kết quả, xử lý khiếu nại nghiêm trọng. |
| `bvh_discipline` | Quản lý chuyên cần, vi phạm, điểm cấu phần I, hồ sơ kỷ luật. |
| `bvh_hr` | Quản lý hồ sơ thành viên, danh sách đa ban, hỗ trợ đối soát. |
| `bcm` | Chấm thái độ và hiệu suất chuyên môn trong phạm vi Ban/Tổ được phân quyền. |
| `member` | Xem điểm cá nhân, xem minh chứng liên quan, gửi đối soát. |

Cần bổ sung phân quyền theo đơn vị, vì role `bcm` hiện tại chưa đủ để phân biệt trưởng/phụ trách từng Ban/Tổ.

## 9. Kế hoạch triển khai

### Phase 0 - Chuẩn hóa yêu cầu

- Chốt tên module: `evaluations`.
- Chốt danh sách tiêu chí từ Quy chế và bảng tiêu chí chi tiết.
- Chuẩn hóa mã tiêu chí: `I.1`, `I.2`, `II.1`, `III-A.1`, `III-B.BCNg.01`, ...
- Xác định mapping Ban/Tổ: BCN, BCNg, BTT, BVH-NS, BVH-KL, BVH-HC, BVH-TC.

### Phase 1 - Schema và migration

- Tạo các bảng lõi cho evaluation.
- Viết migration Alembic.
- Bổ sung index cho `cycle_id`, `member_id`, `criterion_code`, `unit_code`, `status`.
- Giữ `discipline_records` làm legacy.

### Phase 2 - Service tính điểm

- Tạo `EvaluationCalculatorService`.
- Tạo `ClassificationPolicyService`.
- Tạo `EvidenceValidationService`.
- Tách toàn bộ logic tính điểm khỏi router.
- Bảo đảm idempotency khi đồng bộ attendance.

### Phase 3 - API v2

- Tạo router `/api/v2/evaluations`.
- Tạo endpoint quản lý kỳ đánh giá.
- Tạo endpoint ghi nhận score events và evidence.
- Tạo endpoint compute, approve, lock.
- Tạo endpoint xem kết quả theo quyền.

### Phase 4 - Đối soát và phê duyệt

- Tạo workflow appeal.
- Cho thành viên xem kết quả sơ bộ.
- Cho Ban Vận hành xử lý appeal.
- Cho BCN phê duyệt cuối cùng.
- Khóa kỳ đánh giá sau phê duyệt.

### Phase 5 - Migration dữ liệu legacy

- Import `discipline_records.absents` thành legacy absence events.
- Map `discipline_level` khác Không/Khong sang `discipline_cases`.
- Không dùng trực tiếp `kpi` cũ làm điểm quy chế mới; chỉ lưu snapshot hoặc tham chiếu.

### Phase 6 - Test và hardening

- Bổ sung unit test cho calculator.
- Bổ sung integration test cho API.
- Kiểm tra phân quyền.
- Kiểm tra điều kiện chặn.
- Kiểm tra tính điểm đa ban.
- Kiểm tra chống cộng trùng dữ liệu sync.

## 10. Test bắt buộc

| Test | Mục tiêu |
|---|---|
| `test_component_caps` | Không cấu phần nào vượt điểm tối đa. |
| `test_total_score_caps` | Tổng điểm không vượt 100 và không âm. |
| `test_attendance_ratio_i1` | Tính I.1 theo tỷ lệ chuyên cần. |
| `test_unexcused_absence_penalty` | Vắng không phép trừ đúng và tạo blocker. |
| `test_sync_attendance_idempotent` | Gọi sync cùng meeting không cộng trùng. |
| `test_multi_unit_iii_b_weighted_score` | Tính đúng III-B đa ban. |
| `test_classification_blockers` | Điểm cao vẫn bị hạ xếp loại nếu có blocker. |
| `test_member_can_only_view_own_evaluation` | Thành viên chỉ xem điểm của chính mình. |
| `test_appeal_flow` | Gửi, xử lý và lưu kết quả đối soát. |
| `test_evidence_required_for_score_event` | Không ghi nhận điểm khi thiếu minh chứng bắt buộc. |

## 11. Rủi ro kỹ thuật

| Rủi ro | Mức độ | Biện pháp kiểm soát |
|---|---:|---|
| Thay đổi quá lớn làm vỡ frontend hiện tại | Cao | Giữ API v1 legacy, triển khai v2 song song. |
| Tiêu chí thay đổi thường xuyên | Cao | Lưu tiêu chí trong DB/seed, không hard-code. |
| Dữ liệu minh chứng khó chuẩn hóa | Trung bình | Cho phép nhiều loại evidence, nhưng bắt buộc metadata tối thiểu. |
| Sai lệch quyền theo Ban/Tổ | Trung bình | Bổ sung unit-level permission. |
| Cộng trùng điểm đa ban | Cao | Dùng score event, role weight, unique constraint và audit. |
| Kết quả đã duyệt bị sửa trực tiếp | Cao | Lock cycle, chỉ cho điều chỉnh qua appeal/event mới. |

## 12. Definition of Done

Module nâng cấp được xem là đạt yêu cầu tối thiểu khi:

- Tạo được kỳ đánh giá.
- Import/seed được bộ tiêu chí.
- Ghi nhận được điểm theo tiêu chí và minh chứng.
- Tính được tổng điểm 100 theo cấu phần I, II, III-A, III-B.
- Tính được III-B đa ban theo trọng số.
- Áp dụng được điều kiện chặn xếp loại.
- Thành viên xem được điểm cá nhân và gửi đối soát.
- Ban Vận hành/BCN xử lý, phê duyệt và khóa kỳ đánh giá.
- Có audit log cho hành động quan trọng.
- Có test cho calculator, API và RBAC.
- Không phá API v1 hiện tại trong giai đoạn chuyển đổi.

## 13. Quyết định hiện tại

Phương án triển khai được chọn:

```text
Giữ backend hiện tại.
Không thay toàn bộ src.
Tạo module Evaluation v2 để thay thế dần Discipline legacy.
Giữ `/discipline-records` như API legacy trong ngắn hạn.
Tập trung nâng cấp schema, service tính điểm, minh chứng, đối soát và workflow phê duyệt.
```
