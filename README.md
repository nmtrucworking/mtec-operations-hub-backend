# MTEC Operations Hub Backend (Python)

Backend duoc scaffold bang FastAPI + SQLAlchemy + SQLite theo tai lieu yeu cau trong `docs/BACKEND_REPORT.md`.

## Yeu cau Python

- Khuyen nghi: Python 3.12 (hoac 3.11)
- Khong khuyen nghi Python 3.14 cho stack hien tai vi mot so package co the chua co prebuilt wheel tren Windows.

## 1. Cai dat

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Chay local

```bash
uvicorn app.main:app --reload
```

- Swagger UI: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

Hoac dung script:

```powershell
.\scripts\run_dev.ps1
```

## 3. Cau truc folder

```text
.
|- app/
|  |- core/
|  |- middleware/
|  |- repositories/
|  |- routers/
|  |- services/
|  |- db.py
|  |- deps.py
|  |- main.py
|  |- models.py
|  |- schemas.py
|  |- utils.py
|- alembic/
|  |- versions/
|  |- env.py
|  |- script.py.mako
|- tests/
|- scripts/
|- docs/
|- requirements.txt
|- requirements-dev.txt
|- pyproject.toml
|- alembic.ini
```

Chi tiet: xem `docs/PROJECT_STRUCTURE.md`.

## 4. Tai khoan seed mac dinh

Mat khau chung: `123456Abc!`

- username: bcn, role: bcn
- username: bvh_hr, role: bvh_hr
- username: bvh_finance, role: bvh_finance
- username: bvh_discipline, role: bvh_discipline
- username: bvh_logistics, role: bvh_logistics
- username: bcm, role: bcm
- username: member, role: member

## 5. Cac module da implement (Phase 1 + Phase 2 + mot phan Phase 3)

- Auth: login/logout/me/refresh
- Users: list/create/update/reset-password/status
- Members: list/detail/create/update/status/export csv
- Requests: list/detail/create/update/review
- Transactions: list/pending/create/update/review/soft delete
- Dashboard: overview aggregates
- Assets (Logistics): list/detail/create/update
- Discipline records: list/create/update
- Settings: profile/change-password/notifications
- AI gateway: generate-insight/generate-draft + log metadata

## 6. Business rules da enforce

- RBAC tren endpoint mutating va endpoint review.
- Requests review chi cho role: bcn, bvh_hr.
- Requests -> Finance workflow: tu dong tao linked transaction khi request duoc duyet va co finance draft.
- Transactions:
  - Thu: mac dinh Da duyet.
  - Chi: mac dinh Cho duyet.
  - requiredApprovalRole mapping theo category.
- Finance approval:
  - requiredApprovalRole=bvh_finance => bvh_finance hoac bcn duyet.
  - requiredApprovalRole=bcn => chi bcn duyet.
- Soft delete transaction chi cho bcn, bvh_finance.
- Validation amount > 0, khong review item khong o trang thai Cho duyet.

## 7. Dev workflow

Bootstrap moi truong:

```powershell
.\scripts\bootstrap.ps1
```

Lenh thuong dung:

```bash
pytest
ruff check .
```

Migration voi Alembic:

```bash
alembic revision -m "init"
alembic upgrade head
```

## 8. Ghi chu

- Database hien tai dung SQLite (`mtec_ops.db`) de MVP chay nhanh.
- Da co audit log cho cac hanh dong: CREATE_MEMBER, REVIEW_REQUEST, REVIEW_TRANSACTION, SOFT_DELETE_TRANSACTION.
- Da co rate limit memory-level cho login va AI endpoints.
