"""PostgreSQL-backed job queue (§19.1). Jobs are claimed with FOR UPDATE SKIP LOCKED and survive restarts."""
import logging
import os
import socket
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.settings_store import get_setting
from app.db import SessionLocal, utcnow
from app.models.core import Job

log = logging.getLogger("jobs")

HANDLERS: dict[str, Callable] = {}
STALE_AFTER = timedelta(minutes=5)  # a Processing job with no heartbeat for this long is requeued


class JobCancelled(Exception):
    pass


class QueueFull(Exception):
    pass


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def enqueue(db: Session, kind: str, payload: dict, *, user_id: int | None = None, queue: str = "default",
            ref_type: str = "", ref_id: int | None = None, timeout_seconds: int | None = None,
            max_attempts: int | None = None) -> Job:
    if queue == "rfp":
        limits = get_setting(db, "rfp_limits")
        waiting = db.scalar(select(func.count()).select_from(Job).where(Job.queue == "rfp", Job.status == "Queued"))
        if waiting >= limits["max_queued_jobs"]:
            raise QueueFull(f"The RFP queue is full ({limits['max_queued_jobs']} jobs waiting). Try again later.")
        timeout_seconds = timeout_seconds or limits["job_timeout_seconds"]
        max_attempts = max_attempts or (limits["max_retries"] + 1)
    job = Job(kind=kind, payload=payload, queue=queue, created_by=user_id, ref_type=ref_type, ref_id=ref_id,
              timeout_seconds=timeout_seconds or 1800, max_attempts=max_attempts or 2)
    db.add(job)
    db.flush()
    return job


class JobContext:
    def __init__(self, job_id: int):
        self.job_id = job_id

    def _update(self, **values) -> Job:
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            for k, v in values.items():
                setattr(job, k, v)
            job.heartbeat_at = utcnow()
            s.commit()
            return job

    def progress(self, pct: int, message: str = "") -> None:
        job = self._update(progress=max(0, min(100, pct)), message=message)
        if job.cancel_requested:
            raise JobCancelled()
        if job.started_at and utcnow() > job.started_at + timedelta(seconds=job.timeout_seconds):
            raise TimeoutError(f"Job exceeded its {job.timeout_seconds}s timeout")

    def check(self) -> None:
        """Heartbeat; raises if the job was cancelled or has run past its timeout."""
        job = self._update()
        if job.cancel_requested:
            raise JobCancelled()
        if job.started_at and utcnow() > job.started_at + timedelta(seconds=job.timeout_seconds):
            raise TimeoutError(f"Job exceeded its {job.timeout_seconds}s timeout")


def _claim(db: Session, worker: str) -> Job | None:
    db.execute(text("SELECT pg_advisory_xact_lock(424242)"))  # serialise claims so RFP concurrency is exact
    limits = get_setting(db, "rfp_limits")
    running_rfp = db.scalar(select(func.count()).select_from(Job).where(Job.queue == "rfp", Job.status == "Processing"))
    q = select(Job).where(Job.status == "Queued", Job.run_after <= utcnow())
    if running_rfp >= limits["max_concurrent_jobs"]:
        q = q.where(Job.queue != "rfp")
    job = db.scalar(q.order_by(Job.id).with_for_update(skip_locked=True).limit(1))
    if job:
        job.status = "Processing"
        job.started_at = utcnow()
        job.heartbeat_at = utcnow()
        job.attempts += 1
        job.worker = worker
    db.commit()
    return job


def _requeue_stale(db: Session) -> None:
    cutoff = utcnow() - STALE_AFTER
    for job in db.scalars(select(Job).where(Job.status == "Processing", Job.heartbeat_at < cutoff).with_for_update(skip_locked=True)):
        if job.attempts < job.max_attempts:
            job.status, job.message = "Queued", "Requeued after worker stopped"
        else:
            job.status, job.error, job.finished_at = "Failed", "Worker stopped while processing", utcnow()
    db.commit()


def run_one(worker: str) -> bool:
    with SessionLocal() as db:
        job = _claim(db, worker)
        if not job:
            return False
        job_id, kind = job.id, job.kind
    fn = HANDLERS.get(kind)
    ctx = JobContext(job_id)
    try:
        if fn is None:
            raise RuntimeError(f"No handler registered for job kind '{kind}'")
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            result = fn(db, job, ctx) or {}
            db.commit()
        _finish(job_id, "Completed", result=result)
    except JobCancelled:
        _finish(job_id, "Cancelled", message="Cancelled by user")
        _on_end(job_id, "Cancelled")
    except Exception as e:  # noqa: BLE001
        log.exception("Job %s failed", job_id)
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            retry = job.attempts < job.max_attempts and not isinstance(e, TimeoutError)
            if retry:
                job.status = "Queued"
                job.run_after = utcnow() + timedelta(seconds=30 * job.attempts)
                job.message = f"Retrying after error: {e}"
            else:
                job.status = "Failed"
                job.finished_at = utcnow()
            job.error = f"{e}\n{traceback.format_exc(limit=5)}"
            db.commit()
        if not retry:
            _on_end(job_id, "Failed")
    return True


ON_END: dict[str, Callable] = {}  # kind -> fn(job_id, status) for failure/cancel side effects


def _on_end(job_id: int, status: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        fn = ON_END.get(job.kind)
        if fn:
            try:
                fn(db, job, status)
                db.commit()
            except Exception:  # noqa: BLE001
                log.exception("on_end hook failed for job %s", job_id)


def _finish(job_id: int, status: str, result: dict | None = None, message: str = "") -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        job.status = status
        job.finished_at = datetime.now(timezone.utc)
        if status == "Completed":
            job.progress = 100
        if result is not None:
            job.result = result
        if message:
            job.message = message
        db.commit()


def work_forever(poll_seconds: float = 2.0) -> None:
    import app.handlers  # noqa: F401  registers all job handlers

    worker = f"{socket.gethostname()}:{os.getpid()}"
    log.info("Worker %s started", worker)
    last_stale_check = 0.0
    while True:
        if time.time() - last_stale_check > 60:
            with SessionLocal() as db:
                _requeue_stale(db)
            last_stale_check = time.time()
        try:
            if not run_one(worker):
                time.sleep(poll_seconds)
        except Exception:  # noqa: BLE001
            log.exception("Worker loop error")
            time.sleep(poll_seconds)
