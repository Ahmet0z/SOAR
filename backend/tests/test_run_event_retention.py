from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Automation, AutomationRun, AutomationRunEvent
from app.services import purge_run_events_before, summarize_run_analytics

engine = create_engine("sqlite:///:memory:")
SQLModel.metadata.create_all(engine)


def _create_run(session: Session, automation_id: str) -> AutomationRun:
    run = AutomationRun(automation_id=automation_id, tenant_id="t1", status="pending")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def test_purge_run_events_before_removes_old_records() -> None:
    with Session(engine) as session:
        run = _create_run(session, "auto-1")
        old_event = AutomationRunEvent(
            run_id=run.id,
            tenant_id="t1",
            event_type="queued",
            message="old",
            payload={"automation_id": run.automation_id},
            created_at=datetime.utcnow() - timedelta(days=10),
        )
        recent_event = AutomationRunEvent(
            run_id=run.id,
            tenant_id="t1",
            event_type="success",
            message="recent",
            payload={"automation_id": run.automation_id},
            created_at=datetime.utcnow() - timedelta(days=2),
        )
        session.add(old_event)
        session.add(recent_event)
        session.commit()

        removed = purge_run_events_before(
            session,
            tenant_id="t1",
            cutoff=datetime.utcnow() - timedelta(days=5),
        )
        assert removed == 1
        events = session.exec(select(AutomationRunEvent).where(AutomationRunEvent.run_id == run.id)).all()
        assert len(events) == 1
        assert events[0].event_type == "success"


def test_summarize_run_analytics_builds_retry_profiles() -> None:
    now = datetime.utcnow()
    run_success = AutomationRun(
        id="run-success",
        automation_id="auto-1",
        tenant_id="t1",
        status="success",
        duration_ms=120,
        created_at=now - timedelta(hours=3),
    )
    run_failure = AutomationRun(
        id="run-failure",
        automation_id="auto-1",
        tenant_id="t1",
        status="failed",
        duration_ms=300,
        timed_out=True,
        created_at=now - timedelta(hours=1),
    )
    other_run = AutomationRun(
        id="run-other",
        automation_id="auto-2",
        tenant_id="t1",
        status="failed",
        duration_ms=50,
        created_at=now - timedelta(hours=2),
    )
    events = [
        AutomationRunEvent(
            run_id="run-failure",
            tenant_id="t1",
            event_type="retry_scheduled",
            message="retry",
            payload={"automation_id": "auto-1", "automation_name": "Collector"},
            created_at=now - timedelta(hours=1, minutes=30),
        ),
        AutomationRunEvent(
            run_id="run-failure",
            tenant_id="t1",
            event_type="retry_scheduled",
            message="retry",
            payload={"automation_id": "auto-1", "automation_name": "Collector"},
            created_at=now - timedelta(hours=1, minutes=10),
        ),
    ]
    automations = [
        Automation(
            id="auto-1",
            tenant_id="t1",
            name="Collector",
            description="",
            python_code="def run(payload):\n    return payload",
        ),
        Automation(
            id="auto-2",
            tenant_id="t1",
            name="Notifier",
            description="",
            python_code="def run(payload):\n    return payload",
        ),
    ]
    analytics = summarize_run_analytics(
        [run_success, run_failure, other_run],
        events,
        automations,
        window_hours=24,
        since=now - timedelta(hours=24),
        until=now,
        limit=5,
    )
    assert analytics.total_runs == 3
    assert analytics.total_failures == 2
    top = analytics.automations[0]
    assert top.automation_id == "auto-1"
    assert top.retry_count == 2
    assert top.mean_time_between_retries_ms is not None
    assert top.automation_name == "Collector"
