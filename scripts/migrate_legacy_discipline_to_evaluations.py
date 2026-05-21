from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import EVALUATION_LEGACY_MIGRATION_ENABLED
from app.db import get_session_factory
from app.services.evaluation_legacy_migration import (
    EvaluationLegacyMigrationService,
    generate_migration_batch_id,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate discipline legacy data into evaluation v2."
    )
    parser.add_argument(
        "--mode",
        choices=["inventory", "dry_run", "sandbox", "production", "rollback"],
        required=True,
    )
    parser.add_argument("--cycle-id")
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--member-id")
    parser.add_argument("--migration-batch-id")
    parser.add_argument("--output-dir", default="artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)

    if args.mode in {"dry_run", "sandbox", "production"} and not args.cycle_id:
        raise SystemExit("--cycle-id is required for migration modes")
    if args.mode == "rollback" and not args.migration_batch_id:
        raise SystemExit("--migration-batch-id is required for rollback")
    if args.mode == "production" and not EVALUATION_LEGACY_MIGRATION_ENABLED:
        raise SystemExit(
            "Production migration is disabled. Set EVALUATION_LEGACY_MIGRATION_ENABLED=true."
        )

    db = get_session_factory()()
    try:
        service = EvaluationLegacyMigrationService(db)
        if args.mode == "inventory":
            payload = service.build_inventory()
            prefix = "evaluation_legacy_inventory"
        elif args.mode == "rollback":
            payload = service.soft_rollback(args.migration_batch_id)
            prefix = "evaluation_migration_rollback"
        else:
            payload = service.migrate(
                args.cycle_id,
                mode=args.mode,
                migration_batch_id=args.migration_batch_id
                or generate_migration_batch_id(),
                member_id=args.member_id,
                batch_size=args.batch_size,
            )
            prefix = "evaluation_migration_reconciliation"

        service.write_report(payload, output_dir / f"{prefix}_{timestamp}.json")
        service.write_report(payload, output_dir / f"{prefix}_{timestamp}.md")

        if args.mode == "dry_run":
            db.rollback()
            print("Dry-run completed; no database changes were committed.")
        else:
            db.commit()
            print(f"{args.mode} completed; reports written to {output_dir}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
