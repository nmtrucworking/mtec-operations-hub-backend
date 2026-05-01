# BÁO CÁO CẬP NHẬT HỆ THỐNG BACKEND - VERSION 1.2.0 (MAINTENANCE & VERSIONING)

**Người gửi:** Backend Team  
**Ngày:** 01/05/2026  
**Trạng thái:** Đã triển khai (Production Ready)  
**Phiên bản ứng dụng:** `1.2.0`

---

## 1. Thay đổi quan trọng nhất: API Versioning (v1)
Để đảm bảo tính ổn định và tránh lỗi khi cập nhật các tính năng mới trong tương lai, Backend đã triển khai cấu trúc **API Versioning**.

- **Thay đổi Endpoint:** Toàn bộ các API hiện tại đã được chuyển sang tiền tố `/api/v1/`.
- **Hành động cần thiết từ FE:** Vui lòng cập nhật `baseURL` trong cấu hình kết nối API của Frontend Team.
    - **Cũ:** `http://localhost:8000/api`
    - **Mới:** `http://localhost:8000/api/v1`

*Lợi ích: Giúp Frontend không bị "break" khi Backend nâng cấp lên các phiên bản logic mới (v2, v3...) sau này.*

---

## 2. Nâng cấp hệ thống Nhật ký (Audit Logs Coverage)
Hệ thống Logs hiện đã được mở rộng để bao phủ **100% các hành động thay đổi dữ liệu** trên toàn hệ thống.

- **Các Module mới được bổ sung logs:**
    - **Auth & Settings:** Đăng nhập, Đăng xuất, Đổi mật khẩu, Cập nhật Profile.
    - **Users Management:** Tạo/Sửa User, Reset mật khẩu, Khóa/Mở tài khoản.
    - **Logistics & Discipline:** Mọi thao tác cập nhật tài sản và bản ghi kỷ luật.
    - **Members & Requests:** Các thao tác chỉnh sửa thông tin thành viên và yêu cầu.
- **Dữ liệu Snapshot:** Mỗi bản ghi log hiện lưu trữ chi tiết trạng thái dữ liệu **trước và sau khi thay đổi (Before/After)**, giúp việc truy vết lỗi hoặc thay đổi dữ liệu trở nên cực kỳ chính xác.

---

## 3. Tổng hợp các API mới đã triển khai (v1.2.0)
Dưới đây là danh sách các Endpoint mới sẵn sàng sử dụng tại `/api/v1/...`:

| Module | Endpoint | Mô tả |
|--------|----------|-------|
| **Logs** | `GET /logs` | Xem danh sách nhật ký hoạt động (BCN, BCM) |
| **Logs** | `GET /logs/export` | Xuất CSV nhật ký hoạt động |
| **AI** | `GET /ai/templates` | Lấy danh sách mẫu văn bản hành chính |
| **AI** | `POST /ai/process-context` | Xử lý ngữ cảnh từ file/link |
| **AI** | `POST /ai/export-document` | Xuất file DOCX từ nội dung AI soạn thảo |
| **Assets** | `GET /assets/stats` | Thống kê nhanh tình trạng tài sản |
| **Discipline** | `GET /discipline-records/stats` | Thống kê nhanh KPI và kỷ luật |

---

## 4. Hướng dẫn tích hợp cho Frontend
1. Cập nhật `baseURL` thành `.../api/v1`.
2. Đối với trang **LogsView**, sử dụng API `/api/v1/logs` để hiển thị danh sách hoạt động mới nhất.
3. Kiểm tra các chức năng thống kê tại Dashboard bằng các endpoint `/stats` mới.

---
*Mọi chi tiết về cấu trúc dữ liệu JSON vui lòng tham khảo tài liệu [API_REPORT.md](file:///e:/Workspace/project/mtec-operations-hub-backend/docs/API_REPORT.md) đã được cập nhật.*
