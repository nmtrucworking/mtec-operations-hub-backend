# Phase 6 Implementation Guide - Reporting, Export & Evaluation Dashboard

## 1. Mục tiêu Phase 6

Phase 6 xây dựng lớp báo cáo, xuất dữ liệu và dashboard tổng hợp cho module `evaluations` sau khi hệ thống đã có schema, service tính điểm, API v2, workflow phê duyệt và migration dữ liệu legacy.

Mục tiêu của phase này là biến dữ liệu đánh giá thành thông tin quản trị có thể sử dụng cho Ban Chủ nhiệm, Ban Vận hành, Trưởng ban chuyên môn và thành viên. Báo cáo phải có khả năng truy xuất điểm, minh chứng, điều kiện chặn, đối soát, quyết định phê duyệt và lịch sử thay đổi.

## 2. Đầu vào của Phase 6

Phase 6 giả định các phần sau đã hoàn thành:

- Phase 1: schema lõi cho evaluations.
- Phase 2: calculation engine và classification policy.
- Phase 3: API v2 cho evaluation.
- Phase 4: review, appeal, approval và lock workflow.
- Phase 5: migration dữ liệu legacy và deprecation plan.

Nguồn dữ liệu chính:

- `evaluation_cycles`
- `member_evaluations`
- `member_evaluation_breakdowns`
- `evaluation_criteria`
- `evaluation_score_events`
- `evaluation_evidence`
- `evaluation_appeals`
- `discipline_cases`
- `member_cycle_roles`
- `members`
- `audit_logs`

## 3. Phạm vi thực hiện

### 3.1. Trong phạm vi

| Hạng mục | Mục tiêu |
|---|---|
| Cycle summary dashboard | Tổng quan kỳ đánh giá: số thành viên, điểm trung bình, phân bố xếp loại, trạng thái workflow. |
| Member evaluation report | Báo cáo chi tiết từng thành viên: điểm cấu phần, breakdown tiêu chí, minh chứng, blocker, appeal. |
| Unit report | Báo cáo theo Ban/Tổ: phân bố điểm, xếp loại, chuyên cần, hiệu suất, rủi ro. |
| Discipline and risk report | Báo cáo vi phạm, cảnh cáo, blocker, thành viên cần cải thiện. |
| Appeal report | Báo cáo đối soát: số lượng, trạng thái, thời gian xử lý, tỷ lệ chấp nhận. |
| Export CSV/XLSX | Xuất dữ liệu bảng cho vận hành và đối chiếu. |
| Export PDF/DOCX | Xuất báo cáo chính thức cho lưu trữ hoặc trình BCN. |
| API reporting endpoints | Cung cấp endpoint read-only cho dashboard và export. |
| Caching policy | Tối ưu truy vấn báo cáo nếu dữ liệu lớn. |
| Tests | Test report aggregation, export, RBAC và dữ liệu khóa kỳ. |

### 3.2. Ngoài phạm vi

| Hạng mục | Lý do |
|---|---|
| Frontend UI hoàn chỉnh | Phase này thiết kế backend API/report contract; UI thuộc frontend phase. |
| BI warehouse riêng | Chỉ cần reporting trong app trước, chưa cần data warehouse. |
| Real-time analytics | Không cần cho quy trình đánh giá định kỳ. |
| Machine learning dự đoán rủi ro | Chỉ nên làm sau khi có nhiều kỳ dữ liệu ổn định. |
| Public report | Báo cáo đánh giá là dữ liệu nội bộ, không public. |

## 4. Nguyên tắc thiết kế báo cáo

1. Báo cáo phải đọc từ dữ liệu đã compute và đã lưu, không tự tính công thức khác với `EvaluationCalculatorService`.
2. Báo cáo chính thức chỉ lấy từ cycle `APPROVED` hoặc `LOCKED`, trừ dashboard vận hành nội bộ.
3. Báo cáo phải phân biệt rõ `preliminary_classification` và `final_classification`.
4. Điều kiện chặn phải được hiển thị riêng, không làm mất tổng điểm gốc.
5. Mọi điểm chi tiết phải truy xuất được đến tiêu chí và score events liên quan.
6. Báo cáo cho thành viên chỉ được hiển thị dữ liệu của chính thành viên đó.
7. Báo cáo toàn kỳ chỉ dành cho `bcn`, `bvh_discipline`, `bvh_hr` và các vai trò được phân quyền.
8. Báo cáo theo Ban/Tổ phải tuân thủ unit-level permission.
9. Export phải có metadata: cycle, thời điểm xuất, người xuất, filter, version báo cáo.
10. Không xuất dữ liệu nhạy cảm không cần thiết, ví dụ link nội bộ nhạy cảm hoặc metadata hệ thống nếu người dùng không đủ quyền.

## 5. Phân loại báo cáo

## 5.1. Operational dashboard

Dùng cho Ban Vận hành và BCN theo dõi tiến độ kỳ đánh giá.

Chỉ số chính:

| Metric | Ý nghĩa |
|---|---|
| `totalMembers` | Tổng thành viên thuộc kỳ đánh giá. |
| `computedMembers` | Số thành viên đã có kết quả tính điểm. |
| `approvedMembers` | Số kết quả đã phê duyệt. |
| `lockedMembers` | Số kết quả đã khóa. |
| `openAppeals` | Số appeal chưa xử lý xong. |
| `missingEvidenceEvents` | Số score event thiếu minh chứng bắt buộc. |
| `invalidWeightMembers` | Số thành viên đa ban có trọng số không hợp lệ. |
| `averageTotalScore` | Điểm trung bình toàn kỳ. |
| `classificationDistribution` | Phân bố xếp loại cuối. |
| `unitDistribution` | Phân bố theo Ban/Tổ. |

## 5.2. Official cycle report

Dùng để trình Ban Chủ nhiệm hoặc lưu trữ sau phê duyệt.

Nội dung:

- thông tin kỳ đánh giá;
- danh sách thành viên và xếp loại;
- thống kê tổng quan;
- top contributors;
- danh sách cần cải thiện;
- danh sách không đạt;
- khen thưởng đề xuất;
- nhắc nhở/chế tài đề xuất;
- tổng hợp appeal;
- chữ ký/xác nhận nếu xuất DOCX/PDF.

## 5.3. Member detail report

Dùng cho từng thành viên xem hoặc lưu hồ sơ.

Nội dung:

- thông tin thành viên;
- cycle;
- điểm cấu phần I, II, III-A, III-B;
- tổng điểm;
- xếp loại sơ bộ;
- xếp loại cuối;
- blockers;
- breakdown từng tiêu chí;
- evidence liên quan;
- appeal và kết quả xử lý;
- ghi chú phê duyệt.

## 5.4. Unit report

Dùng cho từng Ban/Tổ.

Nội dung:

- danh sách thành viên thuộc unit trong kỳ;
- điểm trung bình theo cấu phần;
- phân bố xếp loại;
- tỷ lệ chuyên cần;
- số nhiệm vụ/score events;
- số appeal;
- số discipline cases;
- danh sách thành viên rủi ro;
- danh sách thành viên nổi bật.

## 5.5. Risk and discipline report

Dùng cho Ban Vận hành/Tổ Kỷ luật và BCN.

Nội dung:

- danh sách blocker;
- cảnh cáo nội bộ;
- vắng không phép;
- chuyên cần dưới 80%;
- vi phạm nghiêm trọng;
- thành viên cần cải thiện 2 kỳ liên tiếp;
- đề xuất nhắc nhở/cảnh cáo/đình chỉ.

## 5.6. Appeal report

Dùng để đánh giá chất lượng dữ liệu và quy trình đối soát.

Chỉ số:

| Metric | Ý nghĩa |
|---|---|
| `totalAppeals` | Tổng số appeal trong kỳ. |
| `pendingAppeals` | Appeal chờ xử lý. |
| `acceptedAppeals` | Appeal được chấp nhận. |
| `partiallyAcceptedAppeals` | Appeal chấp nhận một phần. |
| `rejectedAppeals` | Appeal bị từ chối. |
| `averageResolutionHours` | Thời gian xử lý trung bình. |
| `appealsByType` | Phân bố theo loại appeal. |
| `appealsByUnit` | Phân bố theo Ban/Tổ. |

## 6. API reporting endpoints đề xuất

Base path:

```text
/api/v2/evaluations/reports
```

## 6.1. Dashboard endpoints

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `GET` | `/cycles/{cycle_id}/dashboard` | manager roles | Tổng quan dashboard kỳ đánh giá. |
| `GET` | `/cycles/{cycle_id}/summary` | manager roles | Summary dạng nhẹ cho card UI. |
| `GET` | `/cycles/{cycle_id}/classification-distribution` | manager roles | Phân bố xếp loại. |
| `GET` | `/cycles/{cycle_id}/component-averages` | manager roles | Điểm trung bình theo cấu phần. |
| `GET` | `/cycles/{cycle_id}/risk-summary` | `bcn`, `bvh_discipline`, `bvh_hr` | Tổng hợp rủi ro/kỷ luật. |

## 6.2. Member report endpoints

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `GET` | `/cycles/{cycle_id}/members/{member_id}` | manager hoặc chính member | Báo cáo chi tiết thành viên. |
| `GET` | `/cycles/{cycle_id}/members/{member_id}/breakdown` | manager hoặc chính member | Breakdown tiêu chí. |
| `GET` | `/cycles/{cycle_id}/members/{member_id}/evidence` | manager hoặc chính member | Minh chứng liên quan. |
| `GET` | `/cycles/{cycle_id}/members/{member_id}/appeals` | manager hoặc chính member | Appeal của thành viên. |

## 6.3. Unit report endpoints

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `GET` | `/cycles/{cycle_id}/units` | manager roles | Tổng quan các Ban/Tổ. |
| `GET` | `/cycles/{cycle_id}/units/{unit_code}` | manager hoặc unit manager | Báo cáo một Ban/Tổ. |
| `GET` | `/cycles/{cycle_id}/units/{unit_code}/members` | manager hoặc unit manager | Danh sách thành viên trong Ban/Tổ. |

## 6.4. Export endpoints

| Method | Endpoint | Role | Mục đích |
|---|---|---|---|
| `GET` | `/cycles/{cycle_id}/exports/members.csv` | manager roles | Export danh sách điểm CSV. |
| `GET` | `/cycles/{cycle_id}/exports/members.xlsx` | manager roles | Export danh sách điểm XLSX. |
| `GET` | `/cycles/{cycle_id}/exports/official-report.docx` | `bcn`, `bvh_discipline`, `bvh_hr` | Export báo cáo chính thức DOCX. |
| `GET` | `/cycles/{cycle_id}/exports/official-report.pdf` | `bcn`, `bvh_discipline`, `bvh_hr` | Export báo cáo chính thức PDF. |
| `GET` | `/cycles/{cycle_id}/members/{member_id}/exports/report.pdf` | manager hoặc chính member | Export báo cáo cá nhân PDF. |

Ghi chú: nếu hệ thống chưa có pipeline PDF ổn định, Phase 6 có thể ưu tiên CSV/XLSX/DOCX trước, PDF làm sau.

## 7. Query filters

Các endpoint list/export nên hỗ trợ filter thống nhất:

| Query param | Ý nghĩa |
|---|---|
| `unitCode` | Lọc Ban/Tổ. |
| `classification` | Lọc xếp loại cuối. |
| `status` | Lọc trạng thái member evaluation. |
| `minScore` | Điểm tối thiểu. |
| `maxScore` | Điểm tối đa. |
| `hasBlocker` | Có điều kiện chặn. |
| `hasAppeal` | Có đối soát. |
| `hasDisciplineCase` | Có hồ sơ kỷ luật. |
| `search` | Tìm theo MSSV/họ tên. |
| `page` | Trang. |
| `pageSize` | Số dòng/trang. |

## 8. Response contract

## 8.1. Cycle dashboard response

```json
{
  "cycleId": "...",
  "cycleCode": "2026-05-MONTHLY",
  "cycleName": "Đánh giá tháng 05/2026",
  "status": "LOCKED",
  "totalMembers": 120,
  "computedMembers": 120,
  "approvedMembers": 120,
  "lockedMembers": 120,
  "averageTotalScore": 82.45,
  "classificationDistribution": {
    "EXCELLENT": 12,
    "GOOD": 47,
    "PASSED": 43,
    "NEEDS_IMPROVEMENT": 14,
    "FAILED": 4
  },
  "componentAverages": {
    "I": 26.4,
    "II": 17.2,
    "III_A": 24.1,
    "III_B": 14.7
  },
  "riskSummary": {
    "attendanceUnder80": 9,
    "internalWarnings": 4,
    "severeViolations": 1,
    "openAppeals": 0
  }
}
```

## 8.2. Member report response

```json
{
  "cycleId": "...",
  "member": {
    "id": "...",
    "mssv": "...",
    "name": "...",
    "ban": "BCNg"
  },
  "scores": {
    "componentI": 27,
    "componentII": 18,
    "componentIIIa": 25,
    "componentIIIb": 17.4,
    "total": 87.4
  },
  "classification": {
    "preliminary": "GOOD",
    "final": "GOOD"
  },
  "blockers": [],
  "breakdowns": [],
  "appeals": [],
  "disciplineCases": []
}
```

## 9. Service cần triển khai

## 9.1. `EvaluationReportService`

File đề xuất:

```text
app/services/evaluation_report.py
```

Trách nhiệm:

- tạo dashboard summary;
- tạo member detail report;
- tạo unit report;
- tạo risk report;
- tạo appeal report;
- chuẩn hóa dữ liệu cho export.

Public methods:

```python
class EvaluationReportService:
    def get_cycle_dashboard(self, cycle_id: str, filters: dict | None = None) -> dict:
        ...

    def get_member_report(self, cycle_id: str, member_id: str) -> dict:
        ...

    def get_unit_report(self, cycle_id: str, unit_code: str, filters: dict | None = None) -> dict:
        ...

    def get_risk_report(self, cycle_id: str, filters: dict | None = None) -> dict:
        ...

    def get_appeal_report(self, cycle_id: str, filters: dict | None = None) -> dict:
        ...
```

## 9.2. `EvaluationExportService`

File đề xuất:

```text
app/services/evaluation_export.py
```

Trách nhiệm:

- export CSV;
- export XLSX;
- export DOCX;
- export PDF nếu pipeline đã sẵn sàng;
- ghi metadata export;
- kiểm soát quyền truy cập nội dung nhạy cảm.

Public methods:

```python
class EvaluationExportService:
    def export_members_csv(self, cycle_id: str, filters: dict | None = None) -> bytes:
        ...

    def export_members_xlsx(self, cycle_id: str, filters: dict | None = None) -> bytes:
        ...

    def export_official_report_docx(self, cycle_id: str, *, actor_user_id: str) -> bytes:
        ...

    def export_official_report_pdf(self, cycle_id: str, *, actor_user_id: str) -> bytes:
        ...

    def export_member_report_pdf(self, cycle_id: str, member_id: str, *, actor_user_id: str) -> bytes:
        ...
```

## 9.3. `EvaluationReportCacheService` optional

File đề xuất:

```text
app/services/evaluation_report_cache.py
```

Chỉ cần nếu dashboard chậm.

Cơ chế:

- cache theo `cycle_id + report_type + filters_hash`;
- invalidate khi compute lại, resolve appeal, approve hoặc lock;
- không cache dữ liệu cá nhân nhạy cảm nếu chưa có policy rõ.

## 10. Export format

## 10.1. CSV members export

Columns đề xuất:

```text
cycle_code,cycle_name,mssv,name,unit_code,role_title,component_i_score,component_ii_score,component_iii_a_score,component_iii_b_score,total_score,preliminary_classification,final_classification,attendance_rate,blockers,status,appeal_count,discipline_case_count
```

## 10.2. XLSX members export

Sheets đề xuất:

| Sheet | Nội dung |
|---|---|
| `Overview` | Metadata kỳ đánh giá và thống kê tổng quan. |
| `Members` | Danh sách điểm thành viên. |
| `Breakdowns` | Điểm theo tiêu chí. |
| `Blockers` | Điều kiện chặn. |
| `Appeals` | Đối soát. |
| `DisciplineCases` | Hồ sơ kỷ luật. |
| `EvidenceSummary` | Tổng hợp minh chứng, không nhất thiết chứa link nhạy cảm. |

## 10.3. Official DOCX/PDF report

Cấu trúc đề xuất:

1. Trang bìa.
2. Thông tin kỳ đánh giá.
3. Căn cứ quy chế.
4. Phương pháp tính điểm.
5. Tổng quan kết quả.
6. Phân bố xếp loại.
7. Kết quả theo Ban/Tổ.
8. Danh sách đề xuất khen thưởng.
9. Danh sách cần cải thiện.
10. Danh sách không đạt hoặc cần xử lý.
11. Tổng hợp đối soát.
12. Tổng hợp blocker/discipline cases.
13. Phụ lục bảng điểm chi tiết.
14. Xác nhận của Ban Vận hành và Ban Chủ nhiệm.

## 10.4. Member PDF report

Cấu trúc đề xuất:

1. Thông tin thành viên.
2. Kỳ đánh giá.
3. Tổng điểm và xếp loại.
4. Điểm theo cấu phần.
5. Breakdown tiêu chí.
6. Minh chứng chính.
7. Điều kiện chặn nếu có.
8. Kết quả đối soát nếu có.
9. Ghi chú phê duyệt.

## 11. Template strategy

Nếu repo đang dùng `docxtpl`, có thể dùng template DOCX.

Thư mục đề xuất:

```text
app/templates/evaluations/official_report.docx
app/templates/evaluations/member_report.docx
```

Quy tắc:

- Không hard-code text báo cáo trong service nếu có thể đưa vào template.
- Template phải version hóa.
- Export metadata cần ghi `templateVersion`.
- Không commit file template chứa thông tin cá nhân thật.

## 12. File cần tạo hoặc chỉnh sửa

```text
app/routers/v2/evaluation_reports.py
app/routers/v2/__init__.py
app/services/evaluation_report.py
app/services/evaluation_export.py
app/services/evaluation_report_cache.py
app/templates/evaluations/README.md
app/templates/evaluations/official_report.docx
app/templates/evaluations/member_report.docx
tests/test_evaluation_reports.py
tests/test_evaluation_exports.py
docs/discipline/PHASE_6_REPORTING_EXPORT_DASHBOARD.md
```

Ghi chú:

- File `.docx` template có thể tạo ở bước triển khai thật, không bắt buộc trong commit tài liệu.
- Nếu chưa có thư viện XLSX, cân nhắc dùng `openpyxl` hoặc export CSV trước.

## 13. RBAC policy

| Action | Role |
|---|---|
| View cycle dashboard | `bcn`, `bvh_discipline`, `bvh_hr` |
| View all member results | `bcn`, `bvh_discipline`, `bvh_hr` |
| View unit report | `bcn`, `bvh_discipline`, `bvh_hr`, `bcm` theo unit |
| View own member report | Chính member |
| Export full cycle CSV/XLSX | `bcn`, `bvh_discipline`, `bvh_hr` |
| Export official DOCX/PDF | `bcn`, `bvh_discipline`, `bvh_hr` |
| Export own report PDF | Chính member |
| Export risk/discipline report | `bcn`, `bvh_discipline` |
| View appeal report | `bcn`, `bvh_discipline`, `bvh_hr` |

## 14. Privacy and data minimization

Báo cáo có thể chứa dữ liệu nhạy cảm. Cần kiểm soát:

| Dữ liệu | Policy |
|---|---|
| Link minh chứng nội bộ | Chỉ xuất cho manager roles; member chỉ xem link liên quan đến mình. |
| Nội dung vi phạm nghiêm trọng | Chỉ hiển thị chi tiết cho `bcn` và `bvh_discipline`. |
| Appeal content | Chỉ manager hoặc chủ appeal xem. |
| Audit log chi tiết | Không đưa vào report member mặc định. |
| Metadata kỹ thuật | Không xuất nếu không cần. |
| Số điện thoại/email | Chỉ xuất nếu báo cáo cần cho quản trị nhân sự. |

## 15. Performance considerations

Các báo cáo toàn kỳ có thể join nhiều bảng. Cần tối ưu:

- index theo `cycle_id`, `member_id`, `unit_code`, `final_classification`, `status`;
- dùng aggregate query thay vì load toàn bộ nếu chỉ cần summary;
- phân trang danh sách member;
- export lớn dùng streaming response;
- tránh N+1 query khi lấy breakdown/evidence;
- cache dashboard cho cycle `LOCKED` vì dữ liệu không đổi.

## 16. Audit log requirements

| Action | Khi ghi |
|---|---|
| `VIEW_EVALUATION_REPORT` | Khi xem báo cáo nhạy cảm nếu cần audit. |
| `EXPORT_EVALUATION_MEMBERS_CSV` | Khi export CSV. |
| `EXPORT_EVALUATION_MEMBERS_XLSX` | Khi export XLSX. |
| `EXPORT_EVALUATION_OFFICIAL_DOCX` | Khi export DOCX. |
| `EXPORT_EVALUATION_OFFICIAL_PDF` | Khi export PDF. |
| `EXPORT_MEMBER_EVALUATION_REPORT` | Khi export báo cáo cá nhân. |

Không nhất thiết audit mọi lần xem dashboard nếu gây nhiễu log. Bắt buộc audit các export chứa dữ liệu toàn kỳ.

## 17. Error codes đề xuất

| Code | HTTP | Khi dùng |
|---|---:|---|
| `EVALUATION_REPORT_NOT_FOUND` | 404 | Không có dữ liệu báo cáo. |
| `EVALUATION_REPORT_FORBIDDEN` | 403 | Không có quyền xem báo cáo. |
| `EVALUATION_EXPORT_NOT_READY` | 422 | Cycle chưa đủ trạng thái để export chính thức. |
| `EVALUATION_EXPORT_TOO_LARGE` | 413 | Export vượt giới hạn cho phép. |
| `EVALUATION_EXPORT_FAILED` | 500 | Lỗi tạo file. |
| `EVALUATION_TEMPLATE_NOT_FOUND` | 500 | Thiếu template DOCX/PDF. |
| `EVALUATION_REPORT_FILTER_INVALID` | 422 | Filter không hợp lệ. |

## 18. Test bắt buộc Phase 6

File đề xuất:

```text
tests/test_evaluation_reports.py
tests/test_evaluation_exports.py
```

## 18.1. Report service tests

| Test | Mục tiêu |
|---|---|
| `test_cycle_dashboard_counts_members` | Dashboard đếm đúng tổng thành viên. |
| `test_cycle_dashboard_classification_distribution` | Phân bố xếp loại đúng. |
| `test_component_averages_are_correct` | Điểm trung bình cấu phần đúng. |
| `test_member_report_contains_breakdowns` | Báo cáo cá nhân có breakdown. |
| `test_member_report_contains_blockers` | Báo cáo cá nhân hiển thị blocker. |
| `test_unit_report_filters_members_by_unit` | Unit report lọc đúng Ban/Tổ. |
| `test_risk_report_counts_discipline_cases` | Risk report đếm đúng discipline cases. |
| `test_appeal_report_counts_statuses` | Appeal report tổng hợp đúng trạng thái. |

## 18.2. Export tests

| Test | Mục tiêu |
|---|---|
| `test_export_members_csv_has_expected_columns` | CSV có đủ cột chuẩn. |
| `test_export_members_csv_respects_filters` | CSV áp filter đúng. |
| `test_export_members_xlsx_has_expected_sheets` | XLSX có các sheet cần thiết. |
| `test_export_official_report_requires_manager_role` | Role thường không export toàn kỳ. |
| `test_member_can_export_own_report` | Member export báo cáo của chính mình. |
| `test_member_cannot_export_other_member_report` | Member không export báo cáo người khác. |
| `test_locked_cycle_report_is_cacheable` | Cycle locked có thể cache report. |

## 18.3. RBAC tests

| Test | Mục tiêu |
|---|---|
| `test_member_cannot_view_cycle_dashboard` | Member thường không xem dashboard toàn kỳ. |
| `test_bvh_can_view_cycle_dashboard` | BVH xem được dashboard. |
| `test_bcm_can_view_unit_report_only` | BCM chỉ xem unit được phân quyền. |
| `test_bcn_can_export_risk_report` | BCN export được risk report. |
| `test_bvh_hr_cannot_view_severe_violation_details_if_policy_restricts` | Kiểm tra hạn chế chi tiết vi phạm nếu có policy. |

## 19. Manual QA checklist

- [ ] Tạo hoặc chọn cycle đã compute.
- [ ] Xem dashboard toàn kỳ bằng tài khoản BCN.
- [ ] Kiểm tra phân bố xếp loại khớp dữ liệu `member_evaluations`.
- [ ] Xem unit report cho từng Ban/Tổ.
- [ ] Xem member report bằng tài khoản manager.
- [ ] Xem member report bằng tài khoản member chính chủ.
- [ ] Kiểm tra member không xem được báo cáo người khác.
- [ ] Export CSV và kiểm tra encoding tiếng Việt.
- [ ] Export XLSX và kiểm tra sheet/cột.
- [ ] Export official DOCX/PDF nếu đã có template.
- [ ] Kiểm tra export có metadata người xuất và thời điểm xuất.
- [ ] Kiểm tra audit log cho export toàn kỳ.
- [ ] Kiểm tra report cycle locked không thay đổi sau nhiều lần gọi.

## 20. Definition of Done

Phase 6 hoàn thành khi:

- Có service tạo dashboard, member report, unit report, risk report và appeal report.
- Có API read-only cho các báo cáo chính.
- Có export CSV/XLSX cho danh sách điểm thành viên.
- Có export DOCX/PDF hoặc ít nhất thiết kế template sẵn nếu PDF triển khai sau.
- Report tuân thủ RBAC và data minimization.
- Export toàn kỳ có audit log.
- Member chỉ xem/export báo cáo của chính mình.
- Manager xem/export theo đúng phạm vi quyền.
- Có test cho aggregation, export và RBAC.
- Dashboard không tính sai với dữ liệu trong `member_evaluations`.
- API v1 legacy không bị thay đổi hành vi.

## 21. Thứ tự triển khai đề xuất

1. Tạo `EvaluationReportService`.
2. Tạo endpoint dashboard summary.
3. Tạo endpoint member report.
4. Tạo endpoint unit report.
5. Tạo risk report và appeal report.
6. Tạo CSV export.
7. Tạo XLSX export.
8. Thiết kế DOCX templates.
9. Tạo DOCX export.
10. Bổ sung PDF export nếu pipeline ổn định.
11. Bổ sung audit log cho export.
12. Bổ sung cache cho cycle locked nếu cần.
13. Viết tests report/export/RBAC.
14. Chạy `pytest` và `ruff check .`.

## 22. Ghi chú chuyển tiếp sau Phase 6

Sau Phase 6, hệ thống đã có đủ nền để vận hành đánh giá và báo cáo nội bộ. Các phase tiếp theo nên tập trung vào:

- Phase 7: frontend migration hoàn chỉnh sang Evaluation v2.
- Phase 8: hardening RBAC theo unit-level permission.
- Phase 9: monitoring, observability và production hardening.
- Phase 10: archive hoặc loại bỏ module Discipline legacy sau nhiều kỳ ổn định.
