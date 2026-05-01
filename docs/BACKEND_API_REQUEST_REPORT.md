# BÁO CÁO YÊU CẦU CẬP NHẬT API - MTEC OPERATIONS HUB

**Người gửi:** Frontend Team  
**Ngày:** 01/05/2026  
**Dựa trên:** So sánh Codebase hiện tại với `API_REPORT.md` (v2.0)

---

## 1. Module: Nhật ký hoạt động (Activity Logs) - MỚI
Hiện tại hệ thống đã có `LogsView.tsx` nhưng chưa có section API tương ứng trong tài liệu.

### Yêu cầu bổ sung:
- **GET** `/api/logs`: Lấy danh sách nhật ký hoạt động.
    - **Query Params**: `search`, `module` (MEMBERS, FINANCE, LOGISTICS, REQUESTS, SETTINGS, SYSTEM), `action` (CREATE, UPDATE, DELETE, LOGIN, LOGOUT, EXPORT), `page`, `pageSize`.
- **GET** `/api/logs/export`: Xuất dữ liệu nhật ký ra file CSV.
    - **Query Params**: Tương tự như List Logs.

---

## 2. Module: Soạn thảo văn bản AI (AI Generator)
Hệ thống đã phát triển `GeneratorView.tsx` hỗ trợ soạn thảo văn bản hành chính CLB theo mẫu.

### Yêu cầu bổ sung:
- **GET** `/api/ai/templates`: Lấy danh sách các mẫu văn bản hỗ trợ (ví dụ: BM-MTEC-HC-03).
- **POST** `/api/ai/process-context`: Xử lý dữ liệu đầu vào từ file upload hoặc link Google Sheets để cung cấp ngữ cảnh cho AI.
- **POST** `/api/ai/export-document`: Xuất nội dung đã soạn thảo ra file văn bản chính thức (DOCX/PDF).
    - **Body**: `{ content: string, templateId: string, metadata: object }`

---

## 3. Module: Quản lý tài sản (Logistics)
Cần bổ sung API hỗ trợ cho các dropdown và thống kê trong `LogisticsView.tsx`.

### Yêu cầu bổ sung:
- **GET** `/api/assets/categories`: Lấy danh sách các loại tài sản hiện có.
- **GET** `/api/assets/stats`: Lấy thông tin thống kê nhanh (Tổng tài sản, Đang mượn, Cần bảo trì).

---

## 4. Module: Kỷ luật & KPI (Discipline)
Tương tự Logistics, cần API thống kê cho `DisciplineView.tsx`.

### Yêu cầu bổ sung:
- **GET** `/api/discipline-records/stats`: Lấy thống kê (Tổng thành viên, Số ca cảnh cáo, KPI trung bình).

---

## 5. Cập nhật Roles & Permissions
Trong tài liệu `API_REPORT.md` mục **User Roles & Permissions**, cần cập nhật quyền xem Logs:

| Role | Description | Permissions |
|------|-------------|-------------|
| `bcn` | BCN Admin | ... (giữ nguyên) |
| `bcm` | Ban Chuyên môn | Member management, dashboard view, **View Logs** |

---

## 6. Các lưu ý khác
- Các API Export (Members, Logs) nên trả về stream file hoặc link download trực tiếp thay vì JSON dữ liệu thô để tối ưu hiệu năng Frontend.
- Các endpoint AI cần đảm bảo Rate Limit được cấu hình đúng như trong tài liệu (10 requests/60s).

---
*Vui lòng cập nhật tài liệu API_REPORT.md và thông báo cho Frontend Team khi các endpoint này sẵn sàng trên môi trường Development.*
