#!/usr/bin/env python3
"""
Migrate EventParticipant records → Attendance records (event_id path).

Selects all EventParticipant rows whose event has event_type='class',
then creates (or skips existing) Attendance records.

Run from backend dir:
    venv/bin/python scripts/migrate_event_participant_to_attendance.py [--dry-run]

Flags:
    --dry-run   Print stats without writing to DB
    --commit    Actually write (default is dry-run)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
from datetime import datetime

from src.config import SessionLocal
from src.events.models import Event, EventParticipant, Attendance
from src.services.attendance_service import ep_status_to_attendance_status


PRESENT_STATUSES = {"attended", "late"}
ACTIVE_STATUSES = {"attended", "late", "missed", "absent", "registered"}


def _score_from_status(status: str) -> int:
    """Map attendance status to a numeric score for leaderboard display."""
    if status in ("attended", "present"):
        return 1
    if status == "late":
        return 1
    return 0


def migrate(dry_run: bool = True) -> None:
    db = SessionLocal()
    try:
        print("=" * 70)
        print("MIGRATE EventParticipant → Attendance")
        print(f"Mode: {'DRY RUN (no DB changes)' if dry_run else 'COMMIT'}")
        print("=" * 70)

        # All EventParticipant for class events
        class_event_ids = (
            db.query(Event.id)
            .filter(Event.event_type == "class")
            .scalar_subquery()
        )
        participants = (
            db.query(EventParticipant)
            .filter(EventParticipant.event_id.in_(class_event_ids))
            .all()
        )

        print(f"\nFound {len(participants)} EventParticipant rows for class events")

        # Pre-load existing Attendance keys (event_id, user_id) to skip duplicates
        existing_keys = {
            (a.event_id, a.user_id)
            for a in db.query(Attendance.event_id, Attendance.user_id)
            .filter(Attendance.event_id.isnot(None))
            .all()
        }
        print(f"Already migrated: {len(existing_keys)} Attendance rows")

        created = 0
        skipped = 0

        for ep in participants:
            key = (ep.event_id, ep.user_id)
            if key in existing_keys:
                skipped += 1
                continue

            att_status = ep_status_to_attendance_status(ep.registration_status or "registered")
            att_score = _score_from_status(att_status)

            if not dry_run:
                att = Attendance(
                    event_id=ep.event_id,
                    user_id=ep.user_id,
                    status=att_status,
                    score=att_score,
                    activity_score=ep.activity_score,
                )
                db.add(att)
                existing_keys.add(key)

            created += 1

        if not dry_run:
            db.commit()
            print(f"\n✅ Committed {created} new Attendance records")
        else:
            print(f"\nDRY RUN — would create {created} Attendance records, skip {skipped}")

        print(f"Skipped (already exist): {skipped}")
        print("=" * 70)

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate EventParticipant → Attendance")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write to DB (default: dry-run)",
    )
    args = parser.parse_args()
    migrate(dry_run=not args.commit)
