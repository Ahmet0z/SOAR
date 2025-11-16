from sqlmodel import Session, SQLModel, create_engine

from app.automation_runner import process_run, set_runner_engine
from app.models import Automation, AutomationRun


def setup_module(_: object) -> None:
    global engine
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    set_runner_engine(engine)


def _create_automation(session: Session, python_code: str) -> Automation:
    automation = Automation(name="test", description="", python_code=python_code, tenant_id="t1")
    session.add(automation)
    session.commit()
    session.refresh(automation)
    return automation


def test_process_run_records_metrics() -> None:
    with Session(engine) as session:
        automation = _create_automation(session, "def run(payload):\n    return {'value': 42}")
        run = AutomationRun(automation_id=automation.id, tenant_id="t1", timeout_seconds=30)
        session.add(run)
        session.commit()
        should_retry = process_run(run.id)
        assert should_retry is False
        session.refresh(run)
        assert run.status == "success"
        assert run.attempts == 1
        assert run.duration_ms is not None
        assert run.queue_latency_ms is not None


def test_process_run_retries_then_fails() -> None:
    with Session(engine) as session:
        automation = _create_automation(session, "def run(payload):\n    raise ValueError('boom')")
        run = AutomationRun(
            automation_id=automation.id,
            tenant_id="t1",
            timeout_seconds=30,
            max_retries=1,
        )
        session.add(run)
        session.commit()
        assert process_run(run.id) is True
        session.refresh(run)
        assert run.status == "retrying"
        assert run.attempts == 1
        assert process_run(run.id) is False
        session.refresh(run)
        assert run.status == "failed"
        assert run.attempts == 2
        assert run.last_error is not None


def test_process_run_marks_missing_automation() -> None:
    with Session(engine) as session:
        run = AutomationRun(automation_id="missing", tenant_id="t1")
        session.add(run)
        session.commit()
        should_retry = process_run(run.id)
        assert should_retry is False
        session.refresh(run)
        assert run.status == "failed"
        assert run.last_error == "Automation not found"


def test_process_run_marks_timeout_flag() -> None:
    with Session(engine) as session:
        automation = _create_automation(session, "def run(payload):\n    return {'ok': True}")
        run = AutomationRun(
            automation_id=automation.id,
            tenant_id="t1",
            timeout_seconds=0,
        )
        session.add(run)
        session.commit()
        should_retry = process_run(run.id)
        assert should_retry is False
        session.refresh(run)
        assert run.status == "failed"
        assert run.timed_out is True
