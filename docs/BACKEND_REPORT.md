# Bao cao yeu cau Backend - MTEC Operations Hub

Cap nhat: 27/04/2026
Nguon phan tich: toan bo code frontend hien tai (views, hooks, data seed, permissions docs)

## 1. Muc tieu

Tai lieu nay tong hop day du yeu cau backend cho toan bo du an MTEC Operations Hub de backend team co the:
- Thiet ke CSDL va API theo dung nghiep vu hien tai cua frontend.
- Dong bo luong duyet Requests - Finance va RBAC theo vai tro.
- Thay mock data bang du lieu thuc te, co audit va kha nang mo rong.

## 2. Tong quan module can backend hoa

1. Auth + Account/RBAC
2. Dashboard tong hop so lieu
3. Members (nhan su)
4. Requests (don tu)
5. Finance (thu/chi + approval queue + soft delete)
6. Discipline (KPI/chuyen can/ky luat)
7. Logistics (tai san)
8. Generator (luu metadata phat sinh van ban + goi AI service)
9. Settings (profile, doi mat khau, notification, quan ly tai khoan)

## 3. Vai tro va phan quyen (RBAC)

### 3.1 Vai tro he thong
- bcn
- bvh_hr
- bvh_finance
- bvh_discipline
- bvh_logistics
- bcm
- member

### 3.2 Nguyen tac phan quyen can ap dung tai backend
- Backend la noi quyet dinh cuoi cung ve quyen, khong phu thuoc check tren UI.
- Moi endpoint mutating (POST/PATCH/DELETE) phai kiem tra role + ownership.
- Cac hanh dong duyet phai duoc enforce theo role:
  - Request: bcn, bvh_hr
  - Finance approval:
    - Neu requiredApprovalRole = bvh_finance: bvh_finance hoac bcn duyet
    - Neu requiredApprovalRole = bcn: chi bcn duyet
- Soft delete transaction chi cho bcn, bvh_finance.

## 4. Mo hinh du lieu de xuat

## 4.1 users
- id (string/uuid)
- username (unique)
- passwordHash
- fullName
- role (enum)
- avatarInitials
- email
- phone
- isActive
- createdAt, updatedAt

## 4.2 members
- id (string/uuid)
- mssv (unique)
- name
- gender
- dob (date)
- ban
- roleTitle
- status (Active/Inactive)
- phone
- email
- joinDate (date)
- lop
- chuyenNganh
- khoa
- address
- experience
- goal
- orientation
- createdAt, updatedAt

## 4.3 member_skills
- id
- memberId (FK members)
- type (hard|soft)
- name
- level (Tot|Trung binh|Co ban)

## 4.4 requests
- id (format co the giu REQ-xxx cho dong bo UI)
- mssv
- name
- type (Rut khoi CLB|Cam ket trach nhiem|Bao luu sinh hoat)
- date (date)
- reason
- status (Cho duyet|Da duyet|Tu choi)
- reviewer
- reviewedAt (date)
- reviewNote
- linkedTransactionId (nullable)
- financeDraftEnabled (bool)
- financeDraftTitle
- financeDraftAmount
- financeDraftType (Thu|Chi)
- financeDraftCategory
- createdByUserId
- createdAt, updatedAt

## 4.5 transactions
- id (format TX-xxx hoac uuid)
- date (date)
- title
- type (Thu|Chi)
- amount
- owner
- category
- status (Cho duyet|Da duyet|Tu choi)
- requiredApprovalRole (bvh_finance|bcn|null)
- reviewer
- reviewedAt (date)
- approvalNote
- linkedRequestId (nullable)
- linkedRequestType (nullable)
- isDeleted (bool)
- deletedAt (nullable)
- deletedBy (nullable)
- createdByUserId
- createdAt, updatedAt

## 4.6 assets
- id (format TS-xxx hoac uuid)
- name
- quantity
- status (Tot|Moi|Dang muon|Can bao tri)
- holder
- category
- createdAt, updatedAt

## 4.7 discipline_records
- id
- memberId (nullable neu luu theo mssv)
- mssv
- name
- committee
- absents
- kpi
- disciplineLevel (Khong|Nhac nho|Canh cao Lan 1)
- note
- updatedBy
- updatedAt

## 4.8 settings_notifications
- userId
- noti1, noti2, noti3, noti4 (bool)
- updatedAt

## 4.9 ai_generation_logs (khuyen nghi)
- id
- userId
- module (dashboard|generator)
- prompt
- responseText
- provider (gemini)
- status
- createdAt

## 5. API de xuat theo module

Luu y:
- Response nen theo chuan: { data, meta, error }
- Co phan trang + sort + filter cho cac danh sach lon
- Date de xuat dung ISO 8601 o API, frontend co the format ve dd/MM/yyyy

### 5.1 Auth
- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me
- POST /api/auth/refresh

Login response can tra ve:
- accessToken / refreshToken
- user { id, username, fullName, role, avatarInitials }

### 5.2 Accounts/Users (admin)
- GET /api/users?search=&role=&page=&pageSize=
- POST /api/users
- PATCH /api/users/{id}
- POST /api/users/{id}/reset-password
- PATCH /api/users/{id}/status

### 5.3 Members
- GET /api/members?search=&ban=&status=&page=&pageSize=
- GET /api/members/{id}
- POST /api/members
- PATCH /api/members/{id}
- PATCH /api/members/{id}/status
- GET /api/members/export?format=csv&ban=&status=

### 5.4 Requests
- GET /api/requests?search=&type=&status=&page=&pageSize=
- GET /api/requests/{id}
- POST /api/requests
- PATCH /api/requests/{id}
- POST /api/requests/{id}/review

POST /api/requests/{id}/review body:
- status: Da duyet|Tu choi
- reviewNote

Nghiep vu quan trong:
- Khi request duoc duyet va co financeDraftEnabled=true, backend tu tao transaction lien ket (transaction linkedRequestId=request.id), giong logic frontend hien tai.
- Tranh tao transaction trung lap neu request da co linkedTransactionId.

### 5.5 Finance
- GET /api/transactions?search=&type=&status=&fromDate=&toDate=&includeDeleted=false&page=&pageSize=
- GET /api/transactions/pending
- POST /api/transactions
- PATCH /api/transactions/{id}
- POST /api/transactions/{id}/review
- DELETE /api/transactions/{id} (soft delete)

Rules bat buoc:
- type=Thu -> status mac dinh Da duyet
- type=Chi -> status mac dinh Cho duyet
- requiredApprovalRole tinh tu category policy:
  - Su kien, Vat tu, Hoi phi -> bvh_finance
  - Doi ngoai, Thiet bi, Du an lon -> bcn
  - category khac -> mac dinh bvh_finance

POST /api/transactions/{id}/review body:
- status: Da duyet|Tu choi
- reviewNote

### 5.6 Logistics
- GET /api/assets?search=&status=&page=&pageSize=
- GET /api/assets/{id}
- POST /api/assets
- PATCH /api/assets/{id}

### 5.7 Discipline
- GET /api/discipline-records?search=&disciplineLevel=&committee=&page=&pageSize=
- POST /api/discipline-records
- PATCH /api/discipline-records/{id}

### 5.8 Dashboard aggregates
- GET /api/dashboard/overview
Tra ve cac so lieu:
- totalMembers
- currentFund
- totalIncome
- totalExpense
- maintenanceCount
- pendingRequestsCount
- deptDistribution
- recentActivities
- urgentRequests (top N)

### 5.9 Settings
- GET /api/settings/profile
- PATCH /api/settings/profile
- POST /api/settings/change-password
- GET /api/settings/notifications
- PATCH /api/settings/notifications

### 5.10 AI integration gateway
- POST /api/ai/generate-insight
- POST /api/ai/generate-draft

Khuyen nghi:
- Giu API key Gemini o backend, frontend khong goi truc tiep external provider.
- Log prompt/response metadata de truy vet va kiem soat chi phi.

## 6. Workflow nghiep vu quan trong

### 6.1 Workflow Requests -> Finance
1. User tao request (co the kem finance draft).
2. Reviewer (bcn/bvh_hr) duyet request.
3. Neu duyet + co finance draft hop le:
   - Backend tao transaction moi
   - Gan linkedRequestId vao transaction
   - Gan linkedTransactionId vao request
4. Transaction Chi vao pending queue de role phu hop duyet tiep.

### 6.2 Workflow Finance approval
1. Tao giao dich Chi => status Cho duyet.
2. Xac dinh requiredApprovalRole theo category.
3. Reviewer hop le duyet/tu choi.
4. Cap nhat reviewer, reviewedAt, approvalNote.
5. So du quy chi tinh tren giao dich Da duyet va chua bi soft delete.

### 6.3 Soft delete transaction
1. bcn/bvh_finance goi delete transaction.
2. Backend set isDeleted=true, deletedAt, deletedBy.
3. Mac dinh list giao dich khong tra ve record da xoa (tru khi includeDeleted=true).

## 7. Validation va rang buoc

- Amount > 0 cho transaction va finance draft.
- Request bat buoc: mssv, name, type, date, reason.
- Transaction bat buoc: date, title, type, amount, owner, category.
- Neu transaction type=Chi thi approvalNote khong duoc rong.
- Khong cho review item neu status khong phai Cho duyet.
- Khong cho tao linked transaction neu request da lien ket truoc do.
- Validate uniqueness: username, member.mssv.

## 8. Audit log can co

De xuat bang audit_logs:
- id
- actorUserId
- action (CREATE_MEMBER, REVIEW_REQUEST, REVIEW_TRANSACTION, SOFT_DELETE_TRANSACTION, ...)
- resourceType
- resourceId
- beforeSnapshot (json)
- afterSnapshot (json)
- createdAt

## 9. Bao mat va phi chuc nang

- JWT access + refresh token.
- Rate limit cho login va AI endpoints.
- Password hash (bcrypt/argon2), policy do manh mat khau.
- CORS theo env.
- Input validation (schema-level, vd zod/joi/class-validator).
- Pagination bat buoc cho API list.
- Su dung transaction DB cho workflow Request->Transaction de tranh data race.

## 10. Ke hoach trien khai backend de xuat

### Phase 1 (MVP)
- Auth + Users + RBAC middleware
- Members CRUD + export
- Requests CRUD + review
- Transactions CRUD + review + soft delete
- Dashboard overview API

### Phase 2
- Logistics CRUD
- Discipline CRUD
- Settings profile/password/notifications

### Phase 3
- AI gateway + logging + quota guard
- Audit log day du
- Report/export nang cao

## 11. Checklist ban giao giua Frontend va Backend

- [ ] Chot enum values thong nhat (role, status, category, discipline level)
- [ ] Chot format date API (ISO)
- [ ] Chot response schema chung
- [ ] Chot ma loi (error codes) cho tung nghiep vu duyet
- [ ] Chot permission matrix tren endpoint-level
- [ ] Chot quy tac sinh ID (UUID hay prefix business)
- [ ] Chot migration CSDL va seed du lieu ban dau

## 12. Rui ro can luu y

- Frontend hien tai con hardcode/mock o Members, Discipline, Logistics, Settings; can thay bang API theo module.
- Generator va Dashboard AI dang goi provider truc tiep qua service; can dua ve backend de bao mat key.
- Neu khong enforce RBAC tai backend, nguy co bypass phan quyen rat cao.

---

Tai lieu nay co the dung lam baseline cho API contract (OpenAPI/Swagger) va sprint planning cho backend team.