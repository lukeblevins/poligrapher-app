"""Recurring policy acquisition + analysis scheduling.

APScheduler is used only as the in-process timer; the ``Schedule`` DB table is
the source of truth. On startup we re-register a job per enabled schedule, so
schedules survive restarts without relying on APScheduler's own job persistence.

A fired job: resolve the current policy source (services.acquisition) → skip if
the content hash is unchanged → otherwise create a dated Policy and run the
existing generate + score pipeline as a TaskRegistry task, so scheduled runs
appear in the Status Center and reuse its atomic-cancellation machinery.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_registry = None  # TaskRegistry, set in init_scheduler

def cadence_to_trigger(cadence: str) -> CronTrigger:
    """Map a friendly cadence or raw 5-field cron string to a CronTrigger."""
    presets = {
        "daily": CronTrigger(hour=3, minute=0),
        "weekly": CronTrigger(day_of_week="mon", hour=3, minute=0),
        "monthly": CronTrigger(day=1, hour=3, minute=0),
    }
    if cadence in presets:
        return presets[cadence]
    return CronTrigger.from_crontab(cadence)


def init_scheduler(registry) -> None:
    """Start the scheduler and register jobs for all enabled schedules."""
    global _scheduler, _registry
    _registry = registry
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.start()

    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Schedule

    db = SessionLocal()
    try:
        for sched in db.query(Schedule).filter(Schedule.enabled.is_(True)).all():
            try:
                register_job(sched)
            except Exception as exc:  # noqa: BLE001 — a bad cron shouldn't crash boot
                logger.warning("failed to register schedule %s: %s", sched.id, exc)
    finally:
        db.close()
    logger.info("Scheduler started with %d job(s)", len(_scheduler.get_jobs()))


def shutdown_scheduler() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)


def register_job(sched) -> None:
    """Add/replace the timer job for a schedule and persist its next run time."""
    if _scheduler is None:
        return
    trigger = cadence_to_trigger(sched.cadence)
    job = _scheduler.add_job(
        run_schedule_job,
        trigger=trigger,
        args=[str(sched.id)],
        id=str(sched.id),
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    _persist_next_run(str(sched.id), job.next_run_time)


def unregister_job(schedule_id: str) -> None:
    if _scheduler and _scheduler.get_job(schedule_id):
        _scheduler.remove_job(schedule_id)


def trigger_now(schedule_id: str) -> None:
    """Run a schedule immediately on the TaskRegistry thread pool."""
    if _registry is not None:
        task_id = _registry.create(
            kind="schedule", title="Scheduled run", total=1, schedule_id=schedule_id
        )
        _registry.submit(task_id, lambda: run_schedule_job(schedule_id, task_id))


def _persist_next_run(schedule_id: str, when) -> None:
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Schedule

    db = SessionLocal()
    try:
        s = db.get(Schedule, __import__("uuid").UUID(schedule_id))
        if s:
            s.next_run_at = when
            db.commit()
    finally:
        db.close()


def run_schedule_job(schedule_id: str, task_id: str | None = None) -> None:
    """Fired by the timer (or run-now): run the provider's comparison, gated by
    website change detection. Delegates the heavy work to services.runs."""
    import uuid as _uuid

    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Schedule
    from poligrapher_app.services.runs import run_comparison

    # Resolve the provider and mark the schedule running.
    db = SessionLocal()
    try:
        sched = db.get(Schedule, _uuid.UUID(schedule_id))
        if not sched:
            return
        provider_id = sched.provider_id
        provider_name = sched.provider.name
        sched.last_run_at = datetime.now(timezone.utc)
        sched.last_status = "running"
        db.commit()
    finally:
        db.close()

    # Ensure the run shows up in the Status Center even when timer-fired.
    own_task = task_id is None and _registry is not None
    if own_task:
        task_id = _registry.create(kind="schedule", title=f"Scheduled · {provider_name}",
                                   total=1, schedule_id=schedule_id)

    try:
        status = run_comparison(provider_id, scheduled=True, registry=_registry, task_id=task_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("scheduled run failed for %s", schedule_id)
        status = "failed"
        if task_id and _registry:
            _registry.set_failed(task_id, str(exc))
    else:
        if task_id and _registry:
            if status == "cancelled":
                _registry.set_cancelled(task_id)
            elif status == "needs_source":
                _registry.set_failed(task_id, "Could not resolve a policy source")
            else:
                _registry.update(task_id, completed=1)
                _registry.set_done(task_id)

    db = SessionLocal()
    try:
        sched = db.get(Schedule, _uuid.UUID(schedule_id))
        if sched:
            sched.last_status = status
            sched.needs_attention = status == "needs_source"
            db.commit()
    finally:
        db.close()
