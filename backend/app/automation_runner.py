from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from redis import Redis
from redis.exceptions import RedisError
from rq import Queue
from sqlmodel import Session

from .config import get_settings
from .database import engine
from .models import Automation, AutomationRun
from .realtime import publish_tenant_event
from .services import execute_automation_code

settings = get_settings()
runner_engine = engine
_queue: Queue | None = None
PROCESSED_KEY = "automation_runner:processed"
LAST_HEARTBEAT_KEY = "automation_runner:last_heartbeat"
ACTIVE_RUN_KEY = "automation_runner:active_run"


def set_runner_engine(custom_engine) -> None:
    global runner_engine
    runner_engine = custom_engine


def _get_queue() -> Queue:
    global _queue
    if _queue is None:
        connection = Redis.from_url(settings.redis_url)
        _queue = Queue(settings.automation_queue_name, connection=connection)
    return _queue


def _set_runner_meta(key: str, value: str | None) -> None:
    try:
        connection = _get_queue().connection
        if value is None:
            connection.delete(key)
        else:
            connection.set(key, value)
    except RedisError:
        pass


def _increment_processed_runs() -> None:
    try:
        connection = _get_queue().connection
        connection.incr(PROCESSED_KEY)
    except RedisError:
        pass


def _emit_run_event(run: AutomationRun, event_type: str = "run_update") -> None:
    payload = jsonable_encoder(run)
    publish_tenant_event(run.tenant_id, event_type, {"run": payload})


def _emit_metrics_hint(run: AutomationRun) -> None:
    publish_tenant_event(
        run.tenant_id,
        "metrics_refresh",
        {"automation_id": run.automation_id},
    )


def publish_runner_status(tenant_id: str) -> None:
    status = get_runner_status()
    publish_tenant_event(tenant_id, "runner_status", jsonable_encoder(status))


def enqueue_run(run_id: str, tenant_id: str) -> None:
    try:
        queue = _get_queue()
        queue.enqueue(
            run_automation_job,
            args=(run_id,),
            job_id=f"automation-run-{run_id}-{uuid4().hex}",
        )
    except RedisError:
        process_run(run_id)
        with Session(runner_engine) as session:
            run = session.get(AutomationRun, run_id)
            if run:
                publish_runner_status(run.tenant_id)
        return
    publish_tenant_event(tenant_id, "runner_status", jsonable_encoder(get_runner_status()))


def run_automation_job(run_id: str) -> None:
    _set_runner_meta(ACTIVE_RUN_KEY, run_id)
    _set_runner_meta(LAST_HEARTBEAT_KEY, datetime.utcnow().isoformat())
    should_retry = process_run(run_id)
    _increment_processed_runs()
    _set_runner_meta(LAST_HEARTBEAT_KEY, datetime.utcnow().isoformat())
    if should_retry:
        try:
            queue = _get_queue()
            queue.enqueue(
                run_automation_job,
                args=(run_id,),
                job_id=f"automation-run-{run_id}-{uuid4().hex}",
            )
        except RedisError:
            process_run(run_id)
            return
    else:
        _set_runner_meta(ACTIVE_RUN_KEY, "")
    with Session(runner_engine) as session:
        run = session.get(AutomationRun, run_id)
        if run:
            publish_runner_status(run.tenant_id)


def process_run(run_id: str) -> bool:
    with Session(runner_engine) as session:
        run = session.get(AutomationRun, run_id)
        if not run:
            return False
        if run.status not in {"pending", "retrying"}:
            return False
        now = datetime.utcnow()
        if run.queue_latency_ms is None:
            run.queue_latency_ms = int((now - run.created_at).total_seconds() * 1000)
        run.status = "running"
        run.started_at = now
        run.attempts += 1
        run.logs = (run.logs or []) + [f"Deneme {run.attempts} başladı"]
        run.timed_out = False
        run.updated_at = now
        session.add(run)
        session.commit()
        _emit_run_event(run)

        automation = session.get(Automation, run.automation_id)
        if not automation:
            run.status = "failed"
            run.last_error = "Automation not found"
            run.logs = run.logs + ["Otomasyon bulunamadı"]
            run.finished_at = datetime.utcnow()
            run.duration_ms = 0
            run.updated_at = run.finished_at
            run.timed_out = False
            session.add(run)
            session.commit()
            _emit_run_event(run)
            _emit_metrics_hint(run)
            publish_runner_status(run.tenant_id)
            return False

        result = execute_automation_code(automation, run.input_payload)
        run.finished_at = datetime.utcnow()
        elapsed_seconds = (run.finished_at - run.started_at).total_seconds()
        run.duration_ms = int(elapsed_seconds * 1000)
        timed_out = elapsed_seconds > run.timeout_seconds
        run.logs = run.logs + result.logs
        run.updated_at = datetime.utcnow()
        run.timed_out = timed_out

        if result.success and not timed_out:
            run.status = "success"
            run.output = result.output
            run.last_error = None
            session.add(run)
            session.commit()
            _emit_run_event(run)
            _emit_metrics_hint(run)
            publish_runner_status(run.tenant_id)
            return False

        reason = "Timeout exceeded" if timed_out else (result.logs[-1] if result.logs else "Execution failed")
        run.last_error = reason
        run.output = None
        if timed_out:
            run.logs = run.logs + [f"{run.timeout_seconds}sn zaman aşımı aşıldı"]

        if run.attempts <= run.max_retries:
            run.status = "retrying"
            run.logs = run.logs + [
                f"Tekrar denenecek ({run.attempts}/{run.max_retries + 1})",
            ]
            session.add(run)
            session.commit()
            _emit_run_event(run)
            return True

        run.status = "failed"
        session.add(run)
        session.commit()
        _emit_run_event(run)
        _emit_metrics_hint(run)
        publish_runner_status(run.tenant_id)
        return False


def start_runner() -> None:
    try:
        _get_queue().connection.ping()
    except RedisError:
        pass


def get_runner_status() -> Dict[str, Any]:
    try:
        queue = _get_queue()
        connection = queue.connection
        queue_size = queue.count
        processed = int(connection.get(PROCESSED_KEY) or 0)
        last_heartbeat_raw = connection.get(LAST_HEARTBEAT_KEY)
        last_heartbeat = None
        if last_heartbeat_raw:
            last_heartbeat = datetime.fromisoformat(last_heartbeat_raw.decode())
        active_run = connection.get(ACTIVE_RUN_KEY)
        active_run_id = active_run.decode() if active_run else None
        status = "idle"
        if queue_size > 0 or active_run_id:
            status = "running"
        return {
            "queue_size": queue_size,
            "processed_runs": processed,
            "status": status,
            "active_run_id": active_run_id or None,
            "last_heartbeat": last_heartbeat,
        }
    except RedisError:
        return {
            "queue_size": 0,
            "processed_runs": 0,
            "status": "unavailable",
            "active_run_id": None,
            "last_heartbeat": None,
        }


def get_queue() -> Queue:
    return _get_queue()
