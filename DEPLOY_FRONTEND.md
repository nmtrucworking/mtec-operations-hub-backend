# Frontend deploy checklist — Backend env & integration

This file lists the backend environment variables and deployment snippets the Frontend (FE) team needs to configure and verify before deploying the FE to any hosting (Vercel / Netlify / Render).

## API information for FE
- API base URL (set in FE env): `API_BASE_URL` — e.g. `https://api.example.com`
- Health endpoint: `GET /health` -> returns `{"status":"ok"}`
- Auth: login/refresh/me under `/api/auth/*`. Use header `Authorization: Bearer <token>`.

## Required backend envs (ops must set)
- `DATABASE_URL` — Postgres connection string (production). Example: `postgres://user:pass@host:5432/dbname`
- `SECRET_KEY` — JWT secret
- `CORS_ORIGINS` — comma-separated FE origin(s). Example: `https://app.example.com`
- `ENABLE_SEED_DATA` — `0|1` (production: `0`) — seeding is manual
- `AUTO_CREATE_TABLES` — `0|1` (prefer `0` in prod; use migrations)
- `AI_API_KEY` — if AI features are used
- `API_IMAGE` — optional image base URL

FE teams should not set DB credentials locally for production; request the `API_BASE_URL` from backend ops.

## FE env examples
- Vite/React (example): `VITE_API_BASE_URL=https://api.example.com`
- Create React App: `REACT_APP_API_BASE_URL=https://api.example.com`

## Migration & seeding (ops)
- Run migrations once after deploy (CI or manual):
```bash
alembic upgrade head
```
- To seed default users manually (not recommended on startup):
```bash
ENABLE_SEED_DATA=1 python -c "from app.main import _seed_users; _seed_users()"
```

## Health & readiness (FE smoke tests)
1. GET `${API_BASE_URL}/health` -> 200 and `{"status":"ok"}`
2. POST login with test account or create test account
3. Call a protected endpoint with `Authorization` header to verify CORS and auth
4. (If using AI) call AI endpoint and verify latency handling

## Hosting-specific snippets

Render (native Python service)
- Start command:
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
- Health check: `HTTP /health`
- Env: set `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS`, etc. in Render Dashboard

Vercel (if backend used serverless functions)
- We added `vercel.json` + `api/index.py` so Vercel can expose ASGI app. FE should use the Vercel URL as `API_BASE_URL`.

Netlify (if proxying)
- Configure a proxy or use Netlify functions to forward API requests to `API_BASE_URL`.

## CORS guidance for FE
- Ensure FE origin is in backend `CORS_ORIGINS`. Use exact origin (including protocol).

## Notes & security
- Do NOT store `SECRET_KEY`, `AI_API_KEY`, or DB credentials in client-side code. These are server-side secrets.
- Use HTTPS for `API_BASE_URL` in production.
- Default dev seeded accounts (local/dev only): username examples `bcn`, `member` with password `123456Abc!`. Ask backend ops to seed staging explicitly if FE needs them.

## Contact / checklist to send to ops
- Provide FE origin(s) to add to `CORS_ORIGINS`.
- Request `API_BASE_URL` and confirmation that migrations and seeding (if needed) are completed.
- Confirm `AI_API_KEY` availability if FE will call AI-backed features.
