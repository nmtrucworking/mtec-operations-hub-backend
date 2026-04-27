# Deployment Guide

## 1. Production architecture

- `nginx`: reverse proxy on port 80
- `api`: FastAPI container (uvicorn workers)
- `db`: PostgreSQL 16

## 2. Prerequisites on server

- Docker Engine + Docker Compose plugin
- Domain DNS pointed to server IP
- Firewall opened for 80/443
- A folder on server for project files, e.g. `/opt/mtec-operations-hub-backend`

## 3. Environment setup

Create `.env` from template and update secrets:

- `SECRET_KEY`
- `AI_API_KEY`
- `POSTGRES_PASSWORD`
- `CORS_ORIGINS` (frontend domain)
- `API_IMAGE` (for pull-based deploy), for example:
  - `API_IMAGE=ghcr.io/<org-or-user>/mtec-operations-hub-backend:latest`

Recommended production flags:

- `APP_ENV=production`
- `AUTO_CREATE_TABLES=false`
- `ENABLE_SEED_DATA=false`

## 4. First-time deploy

```bash
docker compose -f compose.prod.yml pull
docker compose -f compose.prod.yml up -d
```

Health check:

```bash
curl http://localhost/health
```

## 5. Update deploy

```bash
docker compose -f compose.prod.yml pull
docker compose -f compose.prod.yml up -d
```

## 6. Optional TLS with certbot

Use your preferred TLS flow:

- Option A: terminate TLS at cloud/load-balancer
- Option B: add certbot container and mount certs into nginx

When TLS is enabled, ensure:

- frontend calls backend with `https`
- `CORS_ORIGINS` uses the exact `https://your-domain`

## 7. GitHub Actions secrets

Required repository secrets for `.github/workflows/deploy.yml`:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_PATH`
- `GHCR_USERNAME`
- `GHCR_TOKEN`
