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

    def to_json_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "cycle_id": self.cycle_id,
            "actor_user_id": self.actor_user_id,
            "strict": self.strict,
            "evidence_mode": self.evidence_mode,
            "status": self.status,
            "total_members": self.total_members,
            "processed_members": self.processed_members,
            "computed_members": self.computed_members,
            "skipped_members": self.skipped_members,
            "error": self.error,
            "result": self.result,
            "logs": self.logs,
            "cancel_requested": self.cancel_requested,
            "background_scheduled": self.background_scheduled,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_json_dict(cls, d: dict) -> EvaluationComputeJob:
        return cls(
            job_id=d["job_id"],
            cycle_id=d["cycle_id"],
            actor_user_id=d["actor_user_id"],
            strict=d["strict"],
            evidence_mode=d["evidence_mode"],
            status=d["status"],
            total_members=d["total_members"],
            processed_members=d["processed_members"],
            computed_members=d["computed_members"],
            skipped_members=d["skipped_members"],
            error=d["error"],
            result=d["result"],
            logs=d.get("logs") or [],
            cancel_requested=d["cancel_requested"],
            background_scheduled=d["background_scheduled"],
            created_at=datetime.fromisoformat(d["created_at"]),
            started_at=datetime.fromisoformat(d["started_at"]) if d["started_at"] else None,
            completed_at=datetime.fromisoformat(d["completed_at"]) if d["completed_at"] else None,
            updated_at=datetime.fromisoformat(d["updated_at"]),
        )



class EvaluationComputeJobService:
    _lock = Lock()
    _jobs: dict[str, EvaluationComputeJob] = {}

    @classmethod
    def _get_job_file_path(cls, job_id: str) -> str:
        import os
        from pathlib import Path
        temp_dir = Path("temp") / "compute_jobs"
        os.makedirs(temp_dir, exist_ok=True)
        return str(temp_dir / f"{job_id}.json")

    @classmethod
    def _save_job_to_file(cls, job: EvaluationComputeJob) -> None:
        file_path = cls._get_job_file_path(job.job_id)
        import json
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(job.to_json_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving job {job.job_id} to file: {e}")

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
            cls._save_job_to_file(job)
            return job

    @classmethod
    def get_job(cls, job_id: str) -> EvaluationComputeJob | None:
        file_path = cls._get_job_file_path(job_id)
        import os
        import json
        with cls._lock:
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    job = EvaluationComputeJob.from_json_dict(data)
                    cls._jobs[job_id] = job
                    return job
                except Exception as e:
                    print(f"Error loading job {job_id} from file: {e}")
            return cls._jobs.get(job_id)

    @classmethod
    def cancel_job(cls, job_id: str) -> EvaluationComputeJob | None:
        with cls._lock:
            job = cls.get_job(job_id)
            if not job:
                return None

            if job.status not in TERMINAL_STATUSES:
                job.cancel_requested = True
                job.updated_at = datetime.now(UTC)
                job.logs.append("Da nhan yeu cau huy tu nguoi dung.")
                cls._save_job_to_file(job)
            return job

    @classmethod
    def mark_scheduled(cls, job_id: str) -> bool:
        with cls._lock:
            job = cls.get_job(job_id)
            if not job or job.background_scheduled:
                return False

            job.background_scheduled = True
            job.updated_at = datetime.now(UTC)
            cls._save_job_to_file(job)
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
        import os
        import json
        from pathlib import Path
        temp_dir = Path("temp") / "compute_jobs"
        if temp_dir.exists():
            for filename in os.listdir(temp_dir):
                if filename.endswith(".json"):
                    file_path = temp_dir / filename
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        job = EvaluationComputeJob.from_json_dict(data)
                        if job.cycle_id == cycle_id and job.status not in TERMINAL_STATUSES:
                            return job
                    except Exception as e:
                        print(f"Error loading job from file {file_path}: {e}")
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
            job = cls.get_job(job_id)
            if not job:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            if logs_append:
                job.logs.append(logs_append)
            job.updated_at = datetime.now(UTC)
            cls._save_job_to_file(job)

    @classmethod
    def _trim_finished_jobs(cls) -> None:
        import os
        from pathlib import Path
        temp_dir = Path("temp") / "compute_jobs"
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
            file_path = temp_dir / f"{job.job_id}.json"
            if file_path.exists():
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error removing old job file {file_path}: {e}")
