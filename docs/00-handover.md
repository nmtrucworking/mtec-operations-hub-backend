# 00 — Backend Handover Document

## 1. Mục đích

Tài liệu này dùng để bàn giao backend của hệ thống **MTEC Operations Hub** cho Ban Công nghệ. Nội dung tập trung vào hiện trạng hệ thống, phạm vi bàn giao, checklist tiếp nhận, các vấn đề tồn đọng và roadmap kỹ thuật sau bàn giao.

Repository backend:

```txt
mtec-operations-hub-backend
```

Repository frontend liên quan:

```txt
mtec-operations-hub
```

## 2. Thông tin tổng quan

| Hạng mục | Nội dung |
|---|---|
| Tên hệ thống | MTEC Operations Hub Backend |
| Mục tiêu | Cung cấp API cho hệ thống quản trị vận hành nội bộ CLB MTEC |
| Framework | FastAPI |
| ORM | SQLAlchemy |
| Migration | Alembic |
| Database MVP | SQLite |
| Database production đề xuất | PostgreSQL |
| API docs | Swagger UI / OpenAPI |
| Health check | `/health` |
| API version | `/api/v1`, `/api/v2` |
| Môi trường local mặc định | `http://127.0.0.1:8000` |

## 3. Công nghệ sử dụng

| Nhóm | Công nghệ |
|---|---|
| Backend framework | FastAPI |
| Language | Python |
| Database access | SQLAlchemy |
| Migration | Alembic |
| Validation/schema | Pydantic |
| Authentication | Token-based authentication |
| Authorization | Role-Based Access Control — RBAC |
| Local database | SQLite |
| Production database đề xuất | PostgreSQL |
| Test | Pytest |
| Lint | Ruff |
| Deployment | Docker Compose |

## 4. Cấu trúc thư mục chính

```txt
app/
├── core/            # Config, security, RBAC, audit, response helpers
├── middleware/      # Middleware hệ thống
├── repositories/    # Data access layer nếu có
├── routers/         # API route theo module
├── services/        # Business services
├── db.py            # Database session/engine
├── deps.py          # Dependency injection, auth dependency
├── main.py          # FastAPI app entry
├── models.py        # SQLAlchemy models
├── schemas.py       # Pydantic schemas
└── utils.py         # Utility functions

alembic/
├── versions/
├── env.py
└── script.py.mako

tests/
scripts/
docs/
requirements.txt
requirements-dev.txt
pyproject.toml
alembic.ini
```

## 5. Entry point và endpoint hệ thống

Entry point chính:

```txt
app/main.py
```

Chạy local:

```bash
uvicorn app.main:app --reload
```

Swagger UI:

```txt
http://127.0.0.1:8000/docs
```

Health check:

```http
GET /health
```

Response kỳ vọng:

```json
{
  "status": "ok"
}
```

## 6. Tài khoản seed mặc định

Mật khẩu seed mặc định:

```txt
123456Abc!
```

| Username | Role | Ý nghĩa |
|---|---|---|
| `bcn` | `bcn` | Ban Chủ nhiệm / quản trị cấp cao |
| `bvh_hr` | `bvh_hr` | Ban Vận hành — Nhân sự |
| `bvh_finance` | `bvh_finance` | Ban Vận hành — Tài chính |
| `bvh_discipline` | `bvh_discipline` | Ban Vận hành — Kỷ luật/KPI |
| `bvh_logistics` | `bvh_logistics` | Ban Vận hành — Hậu cần |
| `bcm` | `bcm` | Ban Chuyên môn |
| `member` | `member` | Thành viên thông thường |

> Không giữ mật khẩu seed mặc định khi triển khai production.

## 7. Module/API hiện có

| STT | Module | Nhóm API | Trạng thái |
|---:|---|---|---|
| 1 | Auth | `/api/v1/auth` | Đã có |
| 2 | Users | `/api/v1/users` | Đã có |
| 3 | Members | `/api/v1/members` | Đã có |
| 4 | Requests | `/api/v1/requests` | Đã có |
| 5 | Transactions / Finance | `/api/v1/transactions` | Đã có |
| 6 | Dashboard | `/api/v1/dashboard` | Đã có |
| 7 | Assets / Logistics | `/api/v1/assets` | Đã có |
| 8 | Discipline records | `/api/v1/discipline-records` | Đã có |
| 9 | Settings | `/api/v1/settings` | Đã có |
| 10 | AI Gateway | `/api/v1/ai` | Đã có |
| 11 | Logs / Audit | `/api/v1/logs` | Đã có |
| 12 | Competitions | `/api/v1/competitions` | Cần kiểm tra chi tiết |
| 13 | Meetings / Attendance | `/api/v1/meetings` | Cần kiểm tra chi tiết |
| 14 | Evaluations v2 | `/api/v2/evaluations` | Cần kiểm tra chi tiết |

## 8. Business rules chính đã enforce

| Nhóm nghiệp vụ | Quy tắc |
|---|---|
| RBAC | Endpoint thay đổi dữ liệu cần kiểm tra role |
| Request review | Chỉ role phù hợp được duyệt/từ chối yêu cầu |
| Request → Finance | Request được duyệt có thể tạo transaction liên kết nếu có finance draft |
| Finance income | Khoản thu mặc định có thể ở trạng thái đã duyệt |
| Finance expense | Khoản chi mặc định ở trạng thái chờ duyệt |
| Finance approval | Role duyệt phụ thuộc `requiredApprovalRole` |
| Transaction soft delete | Chỉ role phù hợp được xóa mềm giao dịch |
| Validation amount | Số tiền phải lớn hơn 0 |
| Review state | Không review item không ở trạng thái chờ duyệt |
| Audit | Một số hành động quan trọng được ghi log |

## 9. Checklist bàn giao mã nguồn

| STT | Hạng mục | Trạng thái |
|---:|---|---|
| 1 | Ban Công nghệ có quyền truy cập repository backend | [ ] |
| 2 | Clone được repository từ nhánh `main` | [ ] |
| 3 | File `README.md` đã có hướng dẫn cài đặt cơ bản | [ ] |
| 4 | File `.env.example` tồn tại | [ ] |
| 5 | File `requirements.txt` tồn tại | [ ] |
| 6 | File `requirements-dev.txt` tồn tại nếu cần test/lint | [ ] |
| 7 | Thư mục `app/` tồn tại | [ ] |
| 8 | Thư mục `app/routers/` tồn tại | [ ] |
| 9 | Thư mục `app/core/` tồn tại | [ ] |
| 10 | Thư mục `alembic/` tồn tại | [ ] |
| 11 | Thư mục `tests/` tồn tại | [ ] |
| 12 | Thư mục `scripts/` tồn tại | [ ] |

## 10. Checklist chạy local

| STT | Hạng mục | Lệnh / Ghi chú | Trạng thái |
|---:|---|---|---|
| 1 | Tạo virtual environment | `py -3.12 -m venv .venv` | [ ] |
| 2 | Kích hoạt virtual environment | `.venv\Scripts\activate` | [ ] |
| 3 | Cài dependencies | `pip install -r requirements.txt` | [ ] |
| 4 | Copy env mẫu | `copy .env.example .env` | [ ] |
| 5 | Chạy backend local | `uvicorn app.main:app --reload` | [ ] |
| 6 | Mở Swagger UI | `http://127.0.0.1:8000/docs` | [ ] |
| 7 | Kiểm tra health check | `http://127.0.0.1:8000/health` | [ ] |

## 11. Checklist cấu hình môi trường

| Biến môi trường | Ý nghĩa | Bắt buộc production | Trạng thái |
|---|---|---|---|
| `SECRET_KEY` | Khóa ký token/bảo mật | Có | [ ] |
| `DATABASE_URL` | Chuỗi kết nối database | Có | [ ] |
| `CORS_ORIGINS` | Danh sách frontend origin được phép gọi API | Có | [ ] |
| `AI_PROVIDER` | Provider AI nếu bật AI gateway | Tùy tính năng | [ ] |
| `AI_API_KEY` | API key AI | Có nếu dùng AI | [ ] |
| `AUTO_CREATE_TABLES` | Tự tạo bảng khi khởi động | Không khuyến nghị production | [ ] |
| `ENABLE_SEED_DATA` | Seed dữ liệu mẫu | Không khuyến nghị production | [ ] |

## 12. Checklist database

| STT | Hạng mục | Trạng thái |
|---:|---|---|
| 1 | Database local chạy được | [ ] |
| 2 | Alembic config hoạt động | [ ] |
| 3 | Migration chạy được bằng `alembic upgrade head` | [ ] |
| 4 | Seed user mặc định hoạt động nếu bật `ENABLE_SEED_DATA` | [ ] |
| 5 | Có bản backup database hiện tại trước khi bàn giao | [ ] |
| 6 | Chính sách soft delete đã được ghi rõ | [ ] |
| 7 | Có hướng dẫn restore database | [ ] |

## 13. Checklist API

| Nhóm API | Trạng thái kiểm tra |
|---|---|
| Auth | [ ] |
| Users | [ ] |
| Members | [ ] |
| Requests | [ ] |
| Transactions / Finance | [ ] |
| Dashboard | [ ] |
| Assets / Logistics | [ ] |
| Discipline records | [ ] |
| Meetings / Attendance | [ ] |
| Competitions | [ ] |
| Settings | [ ] |
| AI Gateway | [ ] |
| Logs / Audit | [ ] |
| Evaluations v2 | [ ] |

## 14. Checklist phân quyền

| Hạng mục | Trạng thái |
|---|---|
| Role `bcn` có quyền quản trị cao nhất | [ ] |
| Role `bvh_hr` thao tác đúng nghiệp vụ nhân sự | [ ] |
| Role `bvh_finance` thao tác đúng nghiệp vụ tài chính | [ ] |
| Role `bvh_discipline` thao tác đúng nghiệp vụ kỷ luật/KPI | [ ] |
| Role `bvh_logistics` thao tác đúng nghiệp vụ hậu cần | [ ] |
| Role `bcm` có quyền phù hợp với ban chuyên môn | [ ] |
| Role `member` bị giới hạn quyền đúng kỳ vọng | [ ] |
| Endpoint mutating có kiểm tra RBAC backend | [ ] |
| Endpoint review có kiểm tra quyền duyệt | [ ] |

## 15. Checklist bảo mật

| STT | Hạng mục | Trạng thái |
|---:|---|---|
| 1 | Không commit file `.env` thật | [ ] |
| 2 | Không commit secret/API key/password thật | [ ] |
| 3 | `SECRET_KEY` production đã được đổi | [ ] |
| 4 | CORS production không để `*` nếu dùng credential | [ ] |
| 5 | Password seed mặc định đã được đổi hoặc seed đã tắt | [ ] |
| 6 | API AI có rate limit | [ ] |
| 7 | Login có rate limit | [ ] |
| 8 | Audit log ghi nhận thao tác quan trọng | [ ] |

## 16. Checklist kiểm thử

| Lệnh | Mục đích | Trạng thái |
|---|---|---|
| `pytest` | Chạy test | [ ] |
| `ruff check .` | Kiểm tra lint | [ ] |
| `uvicorn app.main:app --reload` | Chạy backend local | [ ] |
| `alembic upgrade head` | Kiểm tra migration | [ ] |

## 17. Known issues

| ID | Vấn đề | Mức | Ảnh hưởng | Hướng xử lý đề xuất |
|---|---|---|---|---|
| BE-KI-001 | SQLite đang dùng cho MVP | P0 | Không phù hợp khi vận hành thật nhiều người dùng | Chuyển PostgreSQL cho production |
| BE-KI-002 | Seed users có password mặc định | P0 | Rủi ro bảo mật | Đổi mật khẩu hoặc tắt seed data |
| BE-KI-003 | Cần xác nhận `SECRET_KEY` production | P0 | Token/session không an toàn nếu dùng key yếu | Dùng secret mạnh, lưu ngoài repo |
| BE-KI-004 | CORS cần giới hạn origin thật | P0 | Rủi ro bị gọi API từ origin không mong muốn | Whitelist frontend domain production |
| BE-KI-005 | Rate limit đang ở memory-level | P1 | Không ổn định nếu scale nhiều instance | Chuyển Redis-based rate limit |
| BE-KI-006 | Auto create tables không phù hợp production ổn định | P1 | Rủi ro lệch schema | Dùng Alembic migration chính thức |
| BE-KI-007 | Audit log cần rà soát độ bao phủ | P1 | Có thể thiếu dấu vết thao tác quan trọng | Lập danh sách event cần audit |
| BE-KI-008 | API docs chưa đủ chi tiết theo module | P1 | Ban Công nghệ khó bảo trì | Viết tài liệu API riêng từng module |
| BE-KI-009 | Cần xác nhận workflow evaluation v2 | P1 | Có thể lệch giữa backend và UI | Test đầy đủ API v2 với nghiệp vụ thật |
| BE-KI-010 | Cần chuẩn hóa backup/restore | P1 | Khó khôi phục dữ liệu khi lỗi | Viết runbook vận hành |

## 18. Roadmap sau bàn giao

### Giai đoạn 1 — Ổn định bàn giao

| Việc cần làm | Ưu tiên |
|---|---|
| Chạy lại toàn bộ backend local theo README | P0 |
| Kiểm tra Swagger UI và health check | P0 |
| Xác nhận `.env.example` đủ biến cần thiết | P0 |
| Hoàn thiện tài liệu API overview | P0 |
| Hoàn thiện permission matrix | P0 |
| Ghi nhận known issues còn lại | P0 |

### Giai đoạn 2 — Chuẩn hóa vận hành

| Việc cần làm | Ưu tiên |
|---|---|
| Chuyển database production sang PostgreSQL | P0 |
| Chuẩn hóa Alembic migration | P1 |
| Chuẩn hóa backup/restore | P1 |
| Chuẩn hóa deployment guide | P1 |
| Rà soát CORS, secret, seed data | P0 |
| Viết runbook xử lý lỗi thường gặp | P1 |

### Giai đoạn 3 — Cải tiến kỹ thuật

| Việc cần làm | Ưu tiên |
|---|---|
| Bổ sung test cho từng router | P1 |
| Tách service/repository rõ hơn nếu module phình to | P2 |
| Chuẩn hóa response schema toàn hệ thống | P2 |
| Chuyển rate limit sang Redis | P2 |
| Mở rộng audit log | P2 |
| Tối ưu query dashboard/statistics | P2 |

## 19. Điều kiện hoàn tất bàn giao

Backend được xem là hoàn tất bàn giao khi:

1. Ban Công nghệ clone được repository.
2. Ban Công nghệ chạy được backend local.
3. Swagger UI hoạt động.
4. Health check trả về `{ "status": "ok" }`.
5. Các tài khoản role mẫu đăng nhập được trong môi trường dev.
6. Các API module chính đã được mô tả hoặc có Swagger để đối chiếu.
7. Các known issues đã được ghi lại.
8. Có roadmap phát triển tiếp theo.
9. Có người phụ trách tiếp nhận repository.
10. Có quy trình quản lý thay đổi sau bàn giao.

## 20. Người tiếp nhận và xác nhận

| Vai trò | Họ tên | Ngày xác nhận | Chữ ký/Ghi chú |
|---|---|---|---|
| Người bàn giao |  |  |  |
| Đại diện Ban Công nghệ |  |  |  |
| Đại diện Ban Chủ nhiệm |  |  |  |
