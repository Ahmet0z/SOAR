from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from .models import (
    Automation,
    AutomationExecutionResult,
    AutomationRun,
    AutomationRunBucket,
    AutomationRunMetrics,
    AuditLog,
    ContextSchemaDefinition,
    Incident,
    Indicator,
    Playbook,
    PlaybookRunResult,
    PlaybookValidationResponse,
    PlaybookEdge,
    PlaybookNode,
)

from .database import engine

SUPPORTED_TYPES = {
    "string": str,
    "integer": int,
    "boolean": bool,
}


def record_audit_log(
    session: Session,
    *,
    tenant_id: str,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    payload: Dict[str, object] | None = None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def _cast_value(field_type: str, value):
    caster = SUPPORTED_TYPES[field_type]
    if field_type == "boolean":
        if isinstance(value, str):
            lowered = value.lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return bool(value)
    return caster(value)


def _fetch_schema(session: Session, tenant_id: str, entity_type: str) -> Dict[str, ContextSchemaDefinition]:
    statement = (
        select(ContextSchemaDefinition)
        .where(
            ContextSchemaDefinition.tenant_id == tenant_id,
            ContextSchemaDefinition.entity_type == entity_type,
            ContextSchemaDefinition.is_active.is_(True),
        )
        .order_by(ContextSchemaDefinition.field_key, ContextSchemaDefinition.version)
    )
    latest: Dict[str, ContextSchemaDefinition] = {}
    for definition in session.exec(statement).all():
        current = latest.get(definition.field_key)
        if current is None or current.version <= definition.version:
            latest[definition.field_key] = definition
    return latest


def validate_context(
    session: Session,
    tenant_id: str,
    entity_type: str,
    context: Dict[str, object],
) -> Dict[str, object]:
    schema = _fetch_schema(session, tenant_id, entity_type)
    normalized: Dict[str, object] = {}
    missing_required = [
        definition.field_key
        for definition in schema.values()
        if definition.required and definition.field_key not in context
    ]
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required fields: {', '.join(missing_required)}",
        )
    for key, value in context.items():
        if key not in schema:
            raise HTTPException(
                status_code=400,
                detail=f"Field '{key}' is not defined in the schema",
            )
        definition = schema[key]
        try:
            normalized[key] = _cast_value(definition.field_type, value)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid value for field '{key}': {value}",
            ) from exc
    return normalized


def validate_context_mutation(
    session: Session,
    tenant_id: str,
    entity_type: str,
    key: str,
    value,
) -> object:
    schema = _fetch_schema(session, tenant_id, entity_type)
    if key not in schema:
        raise HTTPException(status_code=400, detail=f"Field '{key}' is not defined")
    definition = schema[key]
    return _cast_value(definition.field_type, value)


SAFE_GLOBALS = {"__builtins__": {"range": range, "len": len, "min": min, "max": max, "sum": sum}}


def execute_automation_code(automation: Automation, inputs: Dict[str, object]) -> AutomationExecutionResult:
    local_vars: Dict[str, object] = {}
    try:
        exec(automation.python_code, SAFE_GLOBALS.copy(), local_vars)
    except Exception as exc:
        return AutomationExecutionResult(success=False, logs=[f"Compilation error: {exc}"])
    run_fn = local_vars.get("run")
    if not callable(run_fn):
        return AutomationExecutionResult(
            success=False,
            logs=["Automation must define a callable `run` function"],
        )
    try:
        output = run_fn(inputs)
        return AutomationExecutionResult(success=True, logs=["Execution completed"], output=output)
    except Exception as exc:  # pragma: no cover - runtime guard
        return AutomationExecutionResult(success=False, logs=[f"Runtime error: {exc}"])


def validate_playbook(playbook: Playbook) -> PlaybookValidationResponse:
    details: List[str] = []
    node_ids = {node.id for node in playbook.nodes}
    for edge in playbook.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            details.append(f"Edge {edge.id} references missing nodes")
    if not node_ids:
        details.append("Playbook has no nodes")
    if _has_cycle(playbook.nodes, playbook.edges):
        details.append("Playbook contains cycles; execution graph must be acyclic")
    valid = len(details) == 0
    return PlaybookValidationResponse(valid=valid, details=details)


def _has_cycle(nodes: Iterable[PlaybookNode], edges: Iterable[PlaybookEdge]) -> bool:
    adjacency: Dict[str, List[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        adjacency.setdefault(edge.source, []).append(edge.target)
    visiting = set()
    visited = set()

    def dfs(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for neighbor in adjacency.get(node_id, []):
            if dfs(neighbor):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(dfs(node.id) for node in nodes)


def run_playbook(
    playbook: Playbook,
    automations: Dict[str, Automation],
    initial_context: Dict[str, object],
) -> PlaybookRunResult:
    validation = validate_playbook(playbook)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.details)
    context = dict(initial_context)
    log: List[str] = []
    order = _topological_sort(playbook.nodes, playbook.edges)
    for node_id in order:
        node = next((n for n in playbook.nodes if n.id == node_id), None)
        if not node or not node.automation_id:
            continue
        automation = automations.get(node.automation_id)
        if not automation:
            log.append(f"Automation {node.automation_id} missing")
            continue
        result = execute_automation_code(automation, {"context": context})
        log.extend(result.logs)
        if result.success and isinstance(result.output, dict):
            context.update(result.output)
    return PlaybookRunResult(execution_log=log, final_context=context)


def _topological_sort(nodes: Iterable[PlaybookNode], edges: Iterable[PlaybookEdge]) -> List[str]:
    adjacency: Dict[str, List[str]] = {node.id: [] for node in nodes}
    indegree: Dict[str, int] = {node.id: 0 for node in nodes}
    for edge in edges:
        adjacency.setdefault(edge.source, []).append(edge.target)
        indegree[edge.target] = indegree.get(edge.target, 0) + 1
        indegree.setdefault(edge.source, 0)
    queue = [node_id for node_id, deg in indegree.items() if deg == 0]
    order: List[str] = []
    while queue:
        current = queue.pop(0)
        order.append(current)
        for neighbor in adjacency.get(current, []):
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
    return order


def calculate_run_metrics(
    runs: Iterable[AutomationRun],
    *,
    window_hours: int,
    since: datetime,
    until: datetime,
) -> AutomationRunMetrics:
    runs_list = list(runs)
    total_runs = len(runs_list)
    success_count = sum(1 for run in runs_list if run.status == "success")
    failed_count = sum(1 for run in runs_list if run.status == "failed")
    running_count = sum(1 for run in runs_list if run.status == "running")
    pending_count = sum(1 for run in runs_list if run.status in {"pending", "retrying"})
    timeout_count = sum(1 for run in runs_list if run.timed_out)
    durations = [run.duration_ms for run in runs_list if run.duration_ms is not None]
    avg_duration = sum(durations) / len(durations) if durations else None
    latencies = [run.queue_latency_ms for run in runs_list if run.queue_latency_ms is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else None

    bucket_map: Dict[datetime, Dict[str, int]] = defaultdict(
        lambda: {"success": 0, "failed": 0, "running": 0, "pending": 0, "timeouts": 0}
    )
    for run in runs_list:
        bucket_time = run.created_at.replace(minute=0, second=0, microsecond=0)
        bucket = bucket_map[bucket_time]
        if run.status == "success":
            bucket["success"] += 1
        elif run.status == "failed":
            bucket["failed"] += 1
        elif run.status == "running":
            bucket["running"] += 1
        else:
            bucket["pending"] += 1
        if run.timed_out:
            bucket["timeouts"] += 1

    buckets: List[AutomationRunBucket] = []
    cursor = since.replace(minute=0, second=0, microsecond=0)
    end = until.replace(minute=0, second=0, microsecond=0)
    while cursor <= end:
        bucket = bucket_map.get(
            cursor, {"success": 0, "failed": 0, "running": 0, "pending": 0, "timeouts": 0}
        )
        buckets.append(
            AutomationRunBucket(
                bucket_start=cursor,
                success=bucket["success"],
                failed=bucket["failed"],
                running=bucket["running"],
                pending=bucket["pending"],
                timeouts=bucket["timeouts"],
            )
        )
        cursor += timedelta(hours=1)

    return AutomationRunMetrics(
        window_hours=window_hours,
        from_ts=since,
        to_ts=until,
        total_runs=total_runs,
        success_count=success_count,
        failed_count=failed_count,
        running_count=running_count,
        pending_count=pending_count,
        timeout_count=timeout_count,
        avg_duration_ms=avg_duration,
        avg_queue_latency_ms=avg_latency,
        per_hour=buckets,
    )
