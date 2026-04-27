# Project Structure

## Root

- `app/`: FastAPI application source code.
- `alembic/`: Database migration configuration and revisions.
- `tests/`: Unit/integration tests.
- `scripts/`: Helper scripts for local setup and run.
- `docs/`: Requirement and technical documents.

## app/

- `core/`: Config, security, RBAC, response helpers.
- `routers/`: API routes by module.
- `services/`: Business service layer (to be implemented).
- `repositories/`: Data access layer (to be implemented).
- `middleware/`: Custom middlewares (to be implemented).
- `models.py`: SQLAlchemy models.
- `schemas.py`: Pydantic schemas.
- `deps.py`: Dependency injection.
- `db.py`: Database setup.
- `main.py`: FastAPI entrypoint.

## Next suggested conventions

- New business logic should live in `app/services` and be called from routers.
- Keep routers thin; avoid embedding heavy SQL logic directly in route handlers.
- Add migration script for every schema change.
