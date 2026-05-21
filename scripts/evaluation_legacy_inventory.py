from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from app.db import get_session_factory
from app.services.evaluation_legacy_migration import EvaluationLegacyMigrationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build evaluation legacy inventory report.")
    parser.add_argument("--output-dir", default="artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)

    db = get_session_factory()()
    try:
        service = EvaluationLegacyMigrationService(db)
        inventory = service.build_inventory()
        service.write_report(
            inventory,
            output_dir / f"evaluation_legacy_inventory_{timestamp}.json",
        )
        service.write_report(
            inventory,
            output_dir / f"evaluation_legacy_inventory_{timestamp}.md",
        )
        db.commit()
        print(f"Inventory written to {output_dir}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
