from datetime import datetime, timedelta

from app.models import AutomationRun
from app.services import calculate_run_metrics


def test_calculate_run_metrics_produces_hourly_buckets() -> None:
    now = datetime.utcnow()
    runs = [
        AutomationRun(
            automation_id="a1",
            tenant_id="t1",
            status="success",
            duration_ms=120,
            queue_latency_ms=30,
            created_at=now - timedelta(hours=1, minutes=5),
        ),
        AutomationRun(
            automation_id="a1",
            tenant_id="t1",
            status="failed",
            timed_out=True,
            created_at=now - timedelta(minutes=10),
        ),
    ]
    metrics = calculate_run_metrics(
        runs,
        window_hours=2,
        since=now - timedelta(hours=2),
        until=now,
    )
    assert metrics.total_runs == 2
    assert metrics.success_count == 1
    assert metrics.failed_count == 1
    assert metrics.timeout_count == 1
    assert metrics.avg_duration_ms == 120
    assert metrics.avg_queue_latency_ms == 30
    assert len(metrics.per_hour) == 3
    assert sum(bucket.success for bucket in metrics.per_hour) == 1
    assert sum(bucket.failed for bucket in metrics.per_hour) == 1
