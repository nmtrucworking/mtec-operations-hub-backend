# BÁO CÁO CẬP NHẬT BACKEND API - VERSION 1.2.0

**Người gửi:** Backend Team  
**Ngày:** 01/05/2026  
**Trạng thái:** Hoàn thành triển khai  
**Tài liệu chi tiết:** `docs/API_REPORT.md` (v1.2.0)

---

## 1. Danh sách API mới & Cập nhật

### 1.1. Module: Nhật ký hoạt động (Activity Logs) - MỚI
Cung cấp khả năng truy vết toàn bộ hoạt động của hệ thống.
- **GET** `/api/logs`: Lấy danh sách nhật ký. Hỗ trợ query: `search`, `module`, `action`, `page`, `pageSize`.
- **GET** `/api/logs/export`: Xuất CSV nhật ký hoạt động.

### 1.2. Module: Soạn thảo văn bản AI (AI Generator)
Mở rộng tính năng hỗ trợ soạn thảo văn bản hành chính.
- **GET** `/api/ai/templates`: Lấy danh sách các mẫu văn bản hỗ trợ (BM-MTEC-HC-03, ...).
- **POST** `/api/ai/process-context`: Gửi text từ file/link để AI trích xuất ngữ cảnh.
- **POST** `/api/ai/export-document`: Xuất nội dung AI đã soạn ra file DOCX chính thức.

### 1.3. Module: Quản lý tài sản (Logistics)
- **GET** `/api/assets/categories`: Lấy danh sách loại tài sản (cho dropdown filter).
- **GET** `/api/assets/stats`: Lấy số liệu thống kê: `total`, `borrowed`, `maintenance`.

### 1.4. Module: Kỷ luật & KPI (Discipline)
- **GET** `/api/discipline-records/stats`: Lấy số liệu thống kê: `totalMembers`, `warnedCases`, `averageKPI`.

### 1.5. Hệ thống Nhật ký (Audit Logs Coverage)
Đã bao phủ toàn bộ hệ thống. Mọi hành động CỦA NGƯỜI DÙNG (Tạo, Sửa, Xóa, Đăng nhập, Đổi mật khẩu) trong các module Members, Users, Assets, Finance, Requests đều được ghi lại snapshot dữ liệu before/after.

---

## 2. Đề xuất cập nhật UI/UX cho Frontend

### 2.1. Dashboard & Thống kê
- **LogisticsView**: Sử dụng `/api/assets/stats` để hiển thị 3 thẻ Card thống kê nhanh ở đầu trang.
- **DisciplineView**: Sử dụng `/api/discipline-records/stats` để hiển thị tổng quan KPI và số ca cảnh cáo.

### 2.2. Activity Logs View
- Triển khai bảng dữ liệu hiển thị: `Thời gian`, `Người thực hiện`, `Hành động`, `Module`, `ID Đối tượng`.
- Thêm bộ lọc nhanh theo Module (MEMBERS, FINANCE, LOGISTICS, ...) và Action (CREATE, UPDATE, DELETE).
- Phân quyền: Chỉ hiển thị menu Logs cho người dùng có role `bcn` hoặc `bcm`.

### 2.3. AI Generator View
- **Template Selection**: Sử dụng `/api/ai/templates` để người dùng chọn mẫu văn bản trước khi soạn thảo.
- **Context Processing**: Thêm UI upload file hoặc dán link Google Sheets, sau đó gọi `/api/ai/process-context` để AI "đọc" dữ liệu trước khi Generate.
- **Export**: Thêm nút "Xuất file văn bản" sau khi AI hoàn thành soạn thảo để tải file DOCX về.

### 2.4. Audit Trail (Optional)
- Ở các trang chi tiết (Member Detail, Request Detail), có thể thêm tab "Lịch sử thay đổi" gọi API Logs với filter `resourceId` để người dùng xem ai đã sửa gì vào lúc nào.

---

## 3. Cập nhật Roles & Permissions
- Role `bcm` (Ban Chuyên môn) hiện đã có quyền **View Logs** và **Export Logs**.

---
*Vui lòng tham khảo file API_REPORT.md v1.2.0 để biết chi tiết cấu trúc JSON Request/Response. Backend đã sẵn sàng trên môi trường Development.*
