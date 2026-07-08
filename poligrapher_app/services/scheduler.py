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
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_registry = None  # TaskRegistry, set in init_scheduler

OUTPUT_BASE = Path(__file__).parent.parent.parent / "output"


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
    """Resolve source → hash-gate → create Policy → generate + score."""
    import uuid as _uuid

    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.mapping import policy_doc_from_db, sync_policy_from_doc
    from poligrapher_app.api.models import Policy, Schedule
    from poligrapher_app.api.utils import provider_slug
    from poligrapher_app.services.acquisition import PolicySourceResolver, provider_domain_from_urls
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_graph
    from poligrapher_app.services.scoring import score_gdpr, score_privacy

    db = SessionLocal()
    try:
        sched = db.get(Schedule, _uuid.UUID(schedule_id))
        if not sched:
            return
        provider = sched.provider
        sched.last_run_at = datetime.now(timezone.utc)
        sched.last_status = "resolving"
        db.commit()

        domain = provider.domain or provider_domain_from_urls([p.url for p in provider.policies])
        if domain and not provider.domain:
            provider.domain = domain
            db.commit()

        resolver = PolicySourceResolver(allow_headless=True)
        resolved = resolver.resolve(provider.name, domain, sched.source_override_url)

        if not resolved:
            sched.last_status = "needs_source"
            sched.needs_attention = True
            db.commit()
            if task_id and _registry:
                _registry.set_failed(task_id, "Could not resolve a policy source")
            return

        sched.last_source_url = resolved.url
        sched.last_strategy = resolved.strategy
        sched.last_confidence = resolved.confidence

        if not resolved.auto and not sched.source_override_url:
            # Low-confidence discovery: don't silently analyze a maybe-wrong page.
            sched.last_status = "needs_confirmation"
            sched.needs_attention = True
            db.commit()
            if task_id and _registry:
                _registry.set_failed(task_id, f"Low-confidence source ({resolved.confidence})")
            return

        if resolved.content_hash == sched.last_content_hash:
            sched.last_status = "unchanged"
            sched.needs_attention = False
            db.commit()
            if task_id and _registry:
                _registry.update(task_id, completed=1)
                _registry.set_done(task_id)
            return

        # Content changed (or first run): capture a new dated Policy and analyze.
        today = date.today()
        output_dir = OUTPUT_BASE / provider_slug(provider.name) / f"{today.isoformat()}_webpage"
        policy = Policy(
            provider_id=provider.id,
            url=resolved.url,
            source="webpage",
            capture_date=today,
            output_dir=str(output_dir),
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)

        doc = policy_doc_from_db(policy)
        should_cancel = (lambda: _registry.is_cancelled(task_id)) if (task_id and _registry) else None
        generate_graph(doc, should_cancel=should_cancel)
        score_privacy(doc)
        score_gdpr(doc)
        sync_policy_from_doc(policy, doc, db)

        sched.last_content_hash = resolved.content_hash
        sched.last_status = "ok"
        sched.needs_attention = False
        db.commit()
        if task_id and _registry:
            _registry.update(task_id, completed=1)
            _registry.set_done(task_id)
    except PipelineCancelled:
        # Cooperative cancel between pipeline stages; staging already discarded.
        logger.info("scheduled run cancelled for %s", schedule_id)
        try:
            sched = db.get(Schedule, _uuid.UUID(schedule_id))
            if sched:
                sched.last_status = "cancelled"
                db.commit()
        except Exception:
            pass
        if task_id and _registry:
            _registry.set_cancelled(task_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("scheduled run failed for %s", schedule_id)
        try:
            sched = db.get(Schedule, _uuid.UUID(schedule_id))
            if sched:
                sched.last_status = "failed"
                db.commit()
        except Exception:
            pass
        if task_id and _registry:
            _registry.set_failed(task_id, str(exc))
    finally:
        db.close()
