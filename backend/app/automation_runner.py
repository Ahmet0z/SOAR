from __future__ import annotations

import threading
from datetime import datetime
from queue import Queue
from typing import Any, Dict

from sqlmodel import Session

from .database import engine
from .models import Automation, AutomationRun
from .services import execute_automation_code

_task_queue: "Queue[str]" = Queue()
_worker_started = False
runner_engine = engine
_worker_state: Dict[str, Any] = {
    "last_heartbeat": None,
    "processed_runs": 0,
    "active_run_id": None,
    "status": "idle",
}


def set_runner_engine(custom_engine) -> None:
    global runner_engine
    runner_engine = custom_engine


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
            return True

        run.status = "failed"
        session.add(run)
        session.commit()
        return False


def _worker() -> None:
    while True:
        run_id = _task_queue.get()
        if run_id is None:
            continue
        _worker_state["active_run_id"] = run_id
        _worker_state["status"] = "running"
        _worker_state["last_heartbeat"] = datetime.utcnow()
        should_retry = process_run(run_id)
        _worker_state["processed_runs"] += 1
        _worker_state["last_heartbeat"] = datetime.utcnow()
        if not should_retry:
            _worker_state["active_run_id"] = None
            _worker_state["status"] = "idle"
        if should_retry:
            _task_queue.put(run_id)


def start_runner() -> None:
    global _worker_started
    if _worker_started:
        return
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    _worker_started = True


def enqueue_run(run_id: str) -> None:
    _task_queue.put(run_id)


def get_runner_status() -> Dict[str, Any]:
    return {
        "queue_size": _task_queue.qsize(),
        "processed_runs": _worker_state["processed_runs"],
        "status": _worker_state["status"],
        "active_run_id": _worker_state["active_run_id"],
        "last_heartbeat": _worker_state["last_heartbeat"],
    }
