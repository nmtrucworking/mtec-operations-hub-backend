# MTEC Operations Hub - API Documentation Report

**Version:** 2.0  
**Last Updated:** April 30, 2026  
**Backend URL:** `http://localhost:8000` (Development) | `https://your-production-url.com` (Production)

---

## Table of Contents

1. [Authentication](#authentication)
2. [API Response Format](#api-response-format)
3. [Rate Limiting](#rate-limiting)
4. [User Roles & Permissions](#user-roles--permissions)
5. [Auth Endpoints](#auth-endpoints)
6. [User Management Endpoints](#user-management-endpoints)
7. [Dashboard Endpoints](#dashboard-endpoints)
8. [Member Management Endpoints](#member-management-endpoints)
9. [Transaction Management Endpoints](#transaction-management-endpoints)
10. [Request Management Endpoints](#request-management-endpoints)
11. [Asset Management Endpoints](#asset-management-endpoints)
12. [Discipline Records Endpoints](#discipline-records-endpoints)
13. [AI Features Endpoints](#ai-features-endpoints)
14. [Settings Endpoints](#settings-endpoints)
15. [Error Handling](#error-handling)
16. [Test Credentials](#test-credentials)

---

## Authentication

### Token-Based Authentication

All endpoints (except `/api/auth/login`) require an **Access Token** in the request header:

```http
Authorization: Bearer {accessToken}
```

### Token Management

- **Access Token:** Valid for a short duration (typically 1 hour)
- **Refresh Token:** Used to obtain a new access token when the current one expires
- **Token Storage:** Store tokens securely (localStorage or secure cookies recommended)

---

## API Response Format

### Success Response

```json
{
  "success": true,
  "data": {
    // Response data here
  },
  "meta": {
    "page": 1,
    "pageSize": 20,
    "total": 100
  }
}
```

### Error Response

```json
{
  "success": false,
  "code": "ERROR_CODE",
  "message": "Error description in Vietnamese",
  "statusCode": 400
}
```

---

## Rate Limiting

### Global Rate Limits

- **Login Endpoint:** 5 requests per 60 seconds per user
- **AI Endpoints:** 10 requests per 60 seconds per user

**Response when rate limit exceeded:**
```http
HTTP/1.1 429 Too Many Requests
```

---

## User Roles & Permissions

| Role | Description | Permissions |
|------|-------------|-------------|
| `bcn` | BCN Admin | Full access to all features |
| `bvh_hr` | BVH HR Staff | User & member management |
| `bvh_finance` | BVH Finance | Transaction approval & management |
| `bvh_discipline` | BVH Discipline | Discipline records management |
| `bvh_logistics` | BVH Logistics | Asset management |
| `bcm` | BCM | Member management, dashboard view |
| `member` | Regular Member | View requests, dashboard, own data |

---

## Auth Endpoints

### 1. Login
**POST** `/api/auth/login`

**Rate Limit:** 5 requests/60s

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIs...",
    "refreshToken": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "id": "USER-001",
      "username": "bcn",
      "fullName": "BCN Admin",
      "role": "bcn",
      "avatarInitials": "BA"
    }
  }
}
```

**Status Codes:**
- `200`: Successful login
- `401`: Invalid credentials
- `403`: Account is disabled

---

### 2. Logout
**POST** `/api/auth/logout`

**Authentication:** Required

**Request Body:**
```json
{
  "refreshToken": "string"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "message": "Da dang xuat"
  }
}
```

---

### 3. Get Current User Info
**GET** `/api/auth/me`

**Authentication:** Required

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "USER-001",
    "username": "bcn",
    "fullName": "BCN Admin",
    "role": "bcn",
    "avatarInitials": "BA"
  }
}
```

---

## User Management Endpoints

### 1. List Users
**GET** `/api/users`

**Authentication:** Required (bcn role)

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | null | Search by username or full name |
| `role` | string | null | Filter by user role |
| `page` | integer | 1 | Page number |
| `pageSize` | integer | 20 | Items per page |

**Example Request:**
```
GET /api/users?search=admin&role=bcn&page=1&pageSize=20
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "USER-001",
      "username": "bcn",
      "fullName": "BCN Admin",
      "role": "bcn",
      "avatarInitials": "BA",
      "email": "bcn@example.com",
      "phone": "0901234567",
      "isActive": true,
      "createdAt": "2024-01-01T00:00:00Z",
      "updatedAt": "2024-01-01T00:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "pageSize": 20,
    "total": 1
  }
}
```

---

### 2. Create User
**POST** `/api/users`

**Authentication:** Required (bcn role)

**Request Body:**
```json
{
  "username": "string",
  "password": "string (min 8 characters)",
  "fullName": "string",
  "role": "string",
  "avatarInitials": "string (optional)",
  "email": "string (optional, valid email)",
  "phone": "string (optional)"
}
```

**Response:** Returns created user object with same structure as list response

---

### 3. Get User Details
**GET** `/api/users/{user_id}`

**Authentication:** Required (bcn role)

---

### 4. Update User
**PATCH** `/api/users/{user_id}`

**Authentication:** Required (bcn role)

**Request Body:**
```json
{
  "fullName": "string (optional)",
  "role": "string (optional)",
  "avatarInitials": "string (optional)",
  "email": "string (optional)",
  "phone": "string (optional)"
}
```

---

### 5. Update User Status
**PATCH** `/api/users/{user_id}/status`

**Authentication:** Required (bcn role)

**Request Body:**
```json
{
  "isActive": true
}
```

---

### 6. Reset User Password
**POST** `/api/users/{user_id}/reset-password`

**Authentication:** Required (bcn role)

**Request Body:**
```json
{
  "newPassword": "string (min 8 characters)"
}
```

---

### 7. Delete User
**DELETE** `/api/users/{user_id}`

**Authentication:** Required (bcn role)

---

## Dashboard Endpoints

### 1. Get Dashboard Overview
**GET** `/api/dashboard/overview`

**Authentication:** Required

**Response:**
```json
{
  "success": true,
  "data": {
    "totalMembers": 150,
    "currentFund": 50000000,
    "totalIncome": 100000000,
    "totalExpense": 50000000,
    "maintenanceCount": 5,
    "pendingRequestsCount": 3,
    "deptDistribution": [
      {
        "ban": "Ban kinh te",
        "count": 45
      }
    ],
    "recentActivities": [
      {
        "action": "CREATE_MEMBER",
        "actor": "bcn",
        "description": "Created new member: John Doe",
        "timestamp": "2024-01-15T10:30:00Z"
      }
    ]
  }
}
```

---

## Member Management Endpoints

### 1. List Members
**GET** `/api/members`

**Authentication:** Required

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | null | Search by name or MSSV |
| `ban` | string | null | Filter by department (ban) |
| `status` | string | null | Filter by status |
| `page` | integer | 1 | Page number |
| `pageSize` | integer | 20 | Items per page |

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "MEM-001",
      "mssv": "20210123",
      "name": "Nguyen Van A",
      "gender": "Nam",
      "dob": "2003-01-15",
      "ban": "Ban kinh te",
      "roleTitle": "Truong ban",
      "status": "Hoat dong",
      "phone": "0901234567",
      "email": "a@example.com",
      "joinDate": "2021-09-15",
      "lop": "K23",
      "chuyenNganh": "Computer Science",
      "khoa": "CNTT",
      "address": "Ha Noi",
      "experience": "2 years",
      "goal": "Developer",
      "orientation": "Tech",
      "createdAt": "2021-09-15T00:00:00Z",
      "updatedAt": "2024-01-15T00:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "pageSize": 20,
    "total": 150
  }
}
```

---

### 2. Get Member Details
**GET** `/api/members/{member_id}`

**Authentication:** Required

---

### 3. Create Member
**POST** `/api/members`

**Authentication:** Required (bcn, bvh_hr roles)

**Request Body:**
```json
{
  "mssv": "string",
  "name": "string",
  "gender": "Nam|Nu",
  "dob": "YYYY-MM-DD",
  "ban": "string",
  "roleTitle": "string",
  "status": "string",
  "phone": "string (optional)",
  "email": "string (optional)",
  "joinDate": "YYYY-MM-DD",
  "lop": "string",
  "chuyenNganh": "string",
  "khoa": "string",
  "address": "string (optional)",
  "experience": "string (optional)",
  "goal": "string (optional)",
  "orientation": "string (optional)"
}
```

---

### 4. Update Member
**PATCH** `/api/members/{member_id}`

**Authentication:** Required (bcn, bvh_hr roles)

**Request Body:** Same as Create Member (all fields optional)

---

### 5. Export Members (CSV/ZIP)
**GET** `/api/members/export?format={csv|zip}`

**Authentication:** Required (bcn, bvh_hr roles)

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | string | `csv` | `csv` for spreadsheet, `zip` for folder of DOCX profiles |
| `ban` | string | null | Filter by department |
| `status` | string | null | Filter by status |

**Response:** File download (CSV or ZIP)

---

### 6. Export Member Profile (DOCX)
**GET** `/api/members/{member_id}/profile`

**Authentication:** Required

**Response:** DOCX file download (Hồ sơ thành viên)

---

### 7. Delete Member
**DELETE** `/api/members/{member_id}`

**Authentication:** Required (bcn, bvh_hr roles)

---

## Transaction Management Endpoints

### 1. List Transactions
**GET** `/api/transactions`

**Authentication:** Required

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | null | Search by title or owner |
| `type` | string | null | Filter by type (Thu/Chi) |
| `status` | string | null | Filter by status |
| `fromDate` | date | null | Start date (YYYY-MM-DD) |
| `toDate` | date | null | End date (YYYY-MM-DD) |
| `includeDeleted` | boolean | false | Include soft-deleted records |
| `page` | integer | 1 | Page number |
| `pageSize` | integer | 20 | Items per page |

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "TX-001",
      "date": "2024-01-15",
      "title": "Mua van phong pham",
      "type": "Chi",
      "amount": 500000,
      "owner": "admin",
      "category": "Office",
      "status": "Da duyet",
      "requiredApprovalRole": "bvh_finance",
      "reviewer": "finance_user",
      "reviewedAt": "2024-01-16T10:00:00Z",
      "approvalNote": "Approved",
      "linkedRequestId": null,
      "linkedRequestType": null,
      "isDeleted": false,
      "deletedAt": null,
      "deletedBy": null,
      "createdByUserId": "USER-001",
      "createdAt": "2024-01-15T09:00:00Z",
      "updatedAt": "2024-01-16T10:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "pageSize": 20,
    "total": 100
  }
}
```

---

### 2. Get Pending Transactions
**GET** `/api/transactions/pending`

**Authentication:** Required

**Response:** List of transactions with status "Cho duyet"

---

### 3. Get Transaction Details
**GET** `/api/transactions/{transaction_id}`

**Authentication:** Required

---

### 4. Create Transaction
**POST** `/api/transactions`

**Authentication:** Required

**Request Body:**
```json
{
  "date": "YYYY-MM-DD",
  "title": "string",
  "type": "Thu|Chi",
  "amount": "number",
  "owner": "string",
  "category": "string",
  "linkedRequestId": "string (optional)",
  "linkedRequestType": "string (optional)"
}
```

---

### 5. Update Transaction
**PATCH** `/api/transactions/{transaction_id}`

**Authentication:** Required

**Request Body:** Same as Create (all fields optional)

---

### 6. Review/Approve Transaction
**POST** `/api/transactions/{transaction_id}/review`

**Authentication:** Required

**Request Body:**
```json
{
  "status": "Da duyet|Tu choi",
  "approvalNote": "string (optional)"
}
```

---

### 7. Soft Delete Transaction
**DELETE** `/api/transactions/{transaction_id}`

**Authentication:** Required

**Note:** Soft delete only - record remains in database with `isDeleted: true`

---

## Request Management Endpoints

### 1. List Requests
**GET** `/api/requests`

**Authentication:** Required

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | null | Search by name or MSSV |
| `type` | string | null | Filter by request type |
| `status` | string | null | Filter by status |
| `page` | integer | 1 | Page number |
| `pageSize` | integer | 20 | Items per page |

**Note:** Members see only their own requests

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "REQ-001",
      "mssv": "20210123",
      "name": "Nguyen Van A",
      "type": "Xin tam ung",
      "date": "2024-01-15",
      "reason": "Binh thuong",
      "status": "Cho duyet",
      "reviewer": null,
      "reviewedAt": null,
      "reviewNote": null,
      "linkedTransactionId": null,
      "financeDraftEnabled": false,
      "financeDraftTitle": null,
      "financeDraftAmount": null,
      "financeDraftType": null,
      "financeDraftCategory": null,
      "createdByUserId": "USER-001",
      "createdAt": "2024-01-15T09:00:00Z",
      "updatedAt": "2024-01-15T09:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "pageSize": 20,
    "total": 50
  }
}
```

---

### 2. Get Request Details
**GET** `/api/requests/{request_id}`

**Authentication:** Required

---

### 3. Create Request
**POST** `/api/requests`

**Authentication:** Required

**Request Body:**
```json
{
  "mssv": "string",
  "name": "string",
  "type": "string",
  "date": "YYYY-MM-DD",
  "reason": "string",
  "financeDraftEnabled": "boolean (optional)",
  "financeDraftTitle": "string (optional)",
  "financeDraftAmount": "number (optional)",
  "financeDraftType": "Thu|Chi (optional)",
  "financeDraftCategory": "string (optional)"
}
```

---

### 4. Update Request
**PATCH** `/api/requests/{request_id}`

**Authentication:** Required

**Request Body:** Same as Create (all fields optional)

---

### 5. Review Request
**POST** `/api/requests/{request_id}/review`

**Authentication:** Required

**Request Body:**
```json
{
  "status": "Da duyet|Tu choi",
  "reviewNote": "string (optional)"
}
```

---

### 6. Delete Request
**DELETE** `/api/requests/{request_id}`

**Authentication:** Required

---

## Asset Management Endpoints

### 1. List Assets
**GET** `/api/assets`

**Authentication:** Required

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | null | Search by asset name |
| `status` | string | null | Filter by status |
| `page` | integer | 1 | Page number |
| `pageSize` | integer | 20 | Items per page |

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "TS-001",
      "name": "Laptop Dell XPS",
      "quantity": 5,
      "status": "Tot",
      "holder": "Admin",
      "category": "Dien thoai",
      "createdAt": "2024-01-01T00:00:00Z",
      "updatedAt": "2024-01-15T00:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "pageSize": 20,
    "total": 30
  }
}
```

---

### 2. Get Asset Details
**GET** `/api/assets/{asset_id}`

**Authentication:** Required

---

### 3. Create Asset
**POST** `/api/assets`

**Authentication:** Required (bcn, bvh_logistics)

**Request Body:**
```json
{
  "name": "string",
  "quantity": "integer",
  "status": "string",
  "holder": "string",
  "category": "string"
}
```

---

### 4. Update Asset
**PATCH** `/api/assets/{asset_id}`

**Authentication:** Required (bcn, bvh_logistics)

**Request Body:** Same as Create (all fields optional)

---

### 5. Delete Asset
**DELETE** `/api/assets/{asset_id}`

**Authentication:** Required (bcn, bvh_logistics)

---

## Discipline Records Endpoints

### 1. List Discipline Records
**GET** `/api/discipline-records`

**Authentication:** Required

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | null | Search by name or MSSV |
| `disciplineLevel` | string | null | Filter by discipline level |
| `committee` | string | null | Filter by committee |
| `page` | integer | 1 | Page number |
| `pageSize` | integer | 20 | Items per page |

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "DR-001",
      "memberId": "MEM-001",
      "mssv": "20210123",
      "name": "Nguyen Van A",
      "committee": "BCN",
      "absents": 2,
      "kpi": 8.5,
      "disciplineLevel": "Tot",
      "note": "Good performance",
      "updatedBy": "USER-001",
      "updatedAt": "2024-01-15T00:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "pageSize": 20,
    "total": 150
  }
}
```

---

### 2. Get Discipline Record Details
**GET** `/api/discipline-records/{record_id}`

**Authentication:** Required

---

### 3. Create Discipline Record
**POST** `/api/discipline-records`

**Authentication:** Required (bcn, bvh_discipline)

**Request Body:**
```json
{
  "memberId": "string",
  "mssv": "string",
  "name": "string",
  "committee": "string",
  "absents": "integer",
  "kpi": "number",
  "disciplineLevel": "string",
  "note": "string (optional)"
}
```

---

### 4. Update Discipline Record
**PATCH** `/api/discipline-records/{record_id}`

**Authentication:** Required (bcn, bvh_discipline)

**Request Body:** Same as Create (all fields optional)

---

### 5. Delete Discipline Record
**DELETE** `/api/discipline-records/{record_id}`

**Authentication:** Required (bcn, bvh_discipline)

---

## AI Features Endpoints

### 1. Generate Insight
**POST** `/api/ai/generate-insight`

**Authentication:** Required

**Rate Limit:** 10 requests/60s

**Request Body:**
```json
{
  "prompt": "string"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "text": "AI generated insight text",
    "logId": "LOG-001",
    "provider": "gemini",
    "status": "success"
  }
}
```

---

### 2. Generate Draft
**POST** `/api/ai/generate-draft`

**Authentication:** Required

**Rate Limit:** 10 requests/60s

**Request Body:**
```json
{
  "prompt": "string",
  "context": "string (optional)"
}
```

**Response:** Same structure as Generate Insight

**Status Codes:**
- `200`: Success
- `429`: Rate limit exceeded
- `500`: AI service error

---

## Settings Endpoints

### 1. Get Profile
**GET** `/api/settings/profile`

**Authentication:** Required

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "USER-001",
    "username": "bcn",
    "fullName": "BCN Admin",
    "role": "bcn",
    "avatarInitials": "BA",
    "email": "bcn@example.com",
    "phone": "0901234567"
  }
}
```

---

### 2. Update Profile
**PATCH** `/api/settings/profile`

**Authentication:** Required

**Request Body:**
```json
{
  "fullName": "string (optional)",
  "avatarInitials": "string (optional)",
  "email": "string (optional)",
  "phone": "string (optional)"
}
```

---

### 3. Change Password
**POST** `/api/settings/change-password`

**Authentication:** Required

**Request Body:**
```json
{
  "currentPassword": "string",
  "newPassword": "string (min 8 characters)"
}
```

**Status Codes:**
- `200`: Password changed successfully
- `400`: Current password incorrect

---

### 4. Get Notification Settings
**GET** `/api/settings/notifications`

**Authentication:** Required

**Response:**
```json
{
  "success": true,
  "data": {
    "emailNotifications": true,
    "pushNotifications": true,
    "smsNotifications": false
  }
}
```

---

### 5. Update Notification Settings
**PATCH** `/api/settings/notifications`

**Authentication:** Required

**Request Body:**
```json
{
  "emailNotifications": "boolean (optional)",
  "pushNotifications": "boolean (optional)",
  "smsNotifications": "boolean (optional)"
}
```

---

## Error Handling

### Common Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `UNAUTHORIZED` | 401 | Missing or invalid authentication token |
| `FORBIDDEN` | 403 | User lacks required permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `BAD_REQUEST` | 400 | Invalid request parameters |
| `CONFLICT` | 409 | Resource already exists |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |

### Error Response Example

```json
{
  "success": false,
  "code": "UNAUTHORIZED",
  "message": "Khong co quyen truy cap",
  "statusCode": 401
}
```

---

## Test Credentials

### Default Test Users

| Username | Password | Role | Full Name |
|----------|----------|------|-----------|
| `bcn` | `123456Abc!` | bcn | BCN Admin |
| `bvh_hr` | `123456Abc!` | bvh_hr | BVH HR |
| `bvh_finance` | `123456Abc!` | bvh_finance | BVH Finance |
| `bvh_discipline` | `123456Abc!` | bvh_discipline | BVH Discipline |
| `bvh_logistics` | `123456Abc!` | bvh_logistics | BVH Logistics |
| `bcm` | `123456Abc!` | bcm | BCM |
| `member` | `123456Abc!` | member | Member |

---

## Frontend Integration Examples

### Login Example (JavaScript/TypeScript)

```typescript
async function login(username: string, password: string) {
  const response = await fetch('http://localhost:8000/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  
  const result = await response.json();
  
  if (result.success) {
    localStorage.setItem('accessToken', result.data.accessToken);
    localStorage.setItem('refreshToken', result.data.refreshToken);
    return result.data.user;
  } else {
    throw new Error(result.message);
  }
}
```

### Authenticated Request Example

```typescript
async function getMembers(page: number = 1, pageSize: number = 20) {
  const token = localStorage.getItem('accessToken');
  
  const response = await fetch(
    `http://localhost:8000/api/members?page=${page}&pageSize=${pageSize}`,
    {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  
  return await response.json();
}
```

### Error Handling Example

```typescript
async function apiCall(url: string, options: RequestInit = {}) {
  const token = localStorage.getItem('accessToken');
  
  const response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  
  const result = await response.json();
  
  if (!result.success) {
    if (response.status === 401) {
      // Token expired or invalid - redirect to login
      window.location.href = '/login';
    } else if (response.status === 403) {
      // User doesn't have permission
      throw new Error('Khong co quyen truy cap');
    } else {
      throw new Error(result.message);
    }
  }
  
  return result.data;
}
```

---

## Additional Notes

### CORS Policy

The backend is configured with CORS to allow requests from frontend applications. Make sure your frontend is running on an allowed origin (configured in `CORS_ORIGINS` environment variable).

### Data Formats

- **Dates:** `YYYY-MM-DD` format for date-only fields
- **DateTime:** ISO 8601 format (`YYYY-MM-DDTHH:mm:ssZ`) for timestamps
- **Amounts:** Integers in Vietnamese Dong (VND), no decimal places
- **Phone:** Can start with 0 or +84

### Pagination

- Minimum `pageSize`: 1
- Maximum `pageSize`: 100 (defaults to 20)
- Page numbering starts from 1

### Soft Deletes

Some endpoints support soft deletes (marked with `isDeleted: true`). Use `includeDeleted` parameter to retrieve soft-deleted records.

---

## Support & Questions

For API-related questions or issues, please contact the backend development team or check the project documentation.

**Last Updated:** April 29, 2026
