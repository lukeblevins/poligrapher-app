"""Run due persisted schedules once, for a scale-to-zero platform job."""

from __future__ import annotations

from datetime import datetime, timezone

from poligrapher_app.api.database import SessionLocal
from poligrapher_app.api.models import Schedule
from poligrapher_app.services.scheduler import cadence_to_trigger
from poligrapher_app.services.tasks import TaskRegistry


def run_due(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    def is_due(value) -> bool:
        if value is None:
            return True
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value <= now

    db = SessionLocal()
    try:
        due = [
            (schedule.id, schedule.cadence)
            for schedule in db.query(Schedule).filter(Schedule.enabled.is_(True)).all()
            if is_due(schedule.next_run_at)
        ]
    finally:
        db.close()

    registry = TaskRegistry()
    for schedule_id, cadence in due:
        task_id = registry.create(kind="schedule", title="Scheduled run", total=1)
        registry.enqueue(task_id, {"kind": "schedule", "schedule_id": str(schedule_id)})
        db = SessionLocal()
        try:
            schedule = db.get(Schedule, schedule_id)
            if schedule and schedule.enabled:
                schedule.next_run_at = cadence_to_trigger(cadence).get_next_fire_time(None, now)
                db.commit()
        finally:
            db.close()
    return len(due)


def main() -> None:
    print(f"Processed {run_due()} due schedule(s).")


if __name__ == "__main__":
    main()
