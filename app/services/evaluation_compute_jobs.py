from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from app.db import get_session_factory
from app.services.evaluation_calculator import EvaluationCalculatorService
from app.services.evaluation_errors import EvaluationError


TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}


@dataclass
class EvaluationComputeJob:
    job_id: str
    cycle_id: str
    actor_user_id: str
    strict: bool
    evidence_mode: str
    status: str = "PENDING"
    total_members: int = 0
    processed_members: int = 0
    computed_members: int = 0
    skipped_members: int = 0
    error: str | None = None
    result: dict | None = None
    logs: list[str] = field(default_factory=list)
    cancel_requested: bool = False
    background_scheduled: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        total = self.total_members or 0
        percent = (
            min(100, round((self.processed_members / total) * 100))
            if total > 0
            else 0
        )
        return {
            "jobId": self.job_id,
            "cycleId": self.cycle_id,
            "status": self.status,
            "totalMembers": self.total_members,
            "processedMembers": self.processed_members,
            "computedMembers": self.computed_members,
            "skippedMembers": self.skipped_members,
            "percent": percent,
            "cancelRequested": self.cancel_requested,
            "error": self.error,
            "result": self.result,
            "logs": self.logs[-30:],
            "createdAt": self.created_at.isoformat(),
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "updatedAt": self.updated_at.isoformat(),
        }


class EvaluationComputeJobService:
    _lock = Lock()
    _jobs: dict[str, EvaluationComputeJob] = {}

    @classmethod
    def create_cycle_job(
        cls,
        *,
        cycle_id: str,
        actor_user_id: str,
        strict: bool,
        evidence_mode: str,
    ) -> EvaluationComputeJob:
        with cls._lock:
            existing = cls._find_active_cycle_job(cycle_id)
            if existing:
                return existing

            cls._trim_finished_jobs()
            job = EvaluationComputeJob(
                job_id=str(uuid4()),
                cycle_id=cycle_id,
                actor_user_id=actor_user_id,
                strict=strict,
                evidence_mode=evidence_mode,
                logs=["Da tao job tinh diem chu ky."],
            )
            cls._jobs[job.job_id] = job
            return job

    @classmethod
    def get_job(cls, job_id: str) -> EvaluationComputeJob | None:
        with cls._lock:
            return cls._jobs.get(job_id)

    @classmethod
    def cancel_job(cls, job_id: str) -> EvaluationComputeJob | None:
        with cls._lock:
            job = cls._jobs.get(job_id)
            if not job:
                return None

            if job.status not in TERMINAL_STATUSES:
                job.cancel_requested = True
                job.updated_at = datetime.now(UTC)
                job.logs.append("Da nhan yeu cau huy tu nguoi dung.")
            return job

    @classmethod
    def mark_scheduled(cls, job_id: str) -> bool:
        with cls._lock:
            job = cls._jobs.get(job_id)
            if not job or job.background_scheduled:
                return False

            job.background_scheduled = True
            job.updated_at = datetime.now(UTC)
            return True

    @classmethod
    def run_cycle_job(cls, job_id: str) -> None:
        cls._update_job(
            job_id,
            status="RUNNING",
            started_at=datetime.now(UTC),
            logs_append="Backend bat dau tinh diem chu ky.",
        )

        session_factory = get_session_factory()
        db = session_factory()
        try:
            service = EvaluationCalculatorService(db)
            total_members = len(service.get_cycle_member_ids(cls._require_job(job_id).cycle_id))
            cls._update_job(job_id, total_members=total_members)

            result = service.compute_cycle(
                cls._require_job(job_id).cycle_id,
                actor_user_id=cls._require_job(job_id).actor_user_id,
                strict=cls._require_job(job_id).strict,
                evidence_mode=cls._require_job(job_id).evidence_mode,
                should_cancel=lambda: bool(cls._require_job(job_id).cancel_requested),
                progress_callback=lambda progress: cls._record_progress(job_id, progress),
            )

            job = cls._require_job(job_id)
            if job.cancel_requested or result.get("cancelled"):
                db.rollback()
                cls._update_job(
                    job_id,
                    status="CANCELLED",
                    result={**result, "persisted": False},
                    completed_at=datetime.now(UTC),
                    logs_append="Da huy job. Cac thay doi chua duoc luu.",
                )
                return

            db.commit()
            cls._update_job(
                job_id,
                status="SUCCEEDED",
                processed_members=result.get("processedMembers", result.get("computedMembers", 0)),
                computed_members=result.get("computedMembers", 0),
                skipped_members=result.get("skippedMembers", 0),
                result={**result, "persisted": True},
                completed_at=datetime.now(UTC),
                logs_append="Hoan tat tinh diem chu ky.",
            )
        except EvaluationError as exc:
            db.rollback()
            cls._update_job(
                job_id,
                status="FAILED",
                error=str(exc),
                completed_at=datetime.now(UTC),
                logs_append=f"Loi tinh diem: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - surfaced through job status
            db.rollback()
            cls._update_job(
                job_id,
                status="FAILED",
                error=str(exc),
                completed_at=datetime.now(UTC),
                logs_append=f"Loi he thong: {exc}",
            )
        finally:
            db.close()

    @classmethod
    def _find_active_cycle_job(cls, cycle_id: str) -> EvaluationComputeJob | None:
        for job in cls._jobs.values():
            if job.cycle_id == cycle_id and job.status not in TERMINAL_STATUSES:
                return job
        return None

    @classmethod
    def _record_progress(cls, job_id: str, progress: dict) -> None:
        processed = progress.get("processedMembers", 0)
        total = progress.get("totalMembers", 0)
        cls._update_job(
            job_id,
            total_members=total,
            processed_members=processed,
            computed_members=progress.get("computedMembers", 0),
            skipped_members=progress.get("skippedMembers", 0),
            logs_append=f"Da xu ly {processed}/{total} thanh vien.",
        )

    @classmethod
    def _require_job(cls, job_id: str) -> EvaluationComputeJob:
        job = cls.get_job(job_id)
        if not job:
            raise RuntimeError(f"Evaluation compute job not found: {job_id}")
        return job

    @classmethod
    def _update_job(cls, job_id: str, **changes) -> None:
        logs_append = changes.pop("logs_append", None)
        with cls._lock:
            job = cls._jobs.get(job_id)
            if not job:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            if logs_append:
                job.logs.append(logs_append)
            job.updated_at = datetime.now(UTC)

    @classmethod
    def _trim_finished_jobs(cls) -> None:
        if len(cls._jobs) <= 100:
            return

        finished = [
            job
            for job in cls._jobs.values()
            if job.status in TERMINAL_STATUSES and job.completed_at is not None
        ]
        finished.sort(key=lambda job: job.completed_at or job.updated_at)
        for job in finished[: len(cls._jobs) - 100]:
            cls._jobs.pop(job.job_id, None)
