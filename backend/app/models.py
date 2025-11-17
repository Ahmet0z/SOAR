from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlmodel import Column, Field as SQLField, JSON, SQLModel


class OrganizationBase(BaseModel):
    slug: str
    name: str


class Organization(SQLModel, OrganizationBase, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)


class OrganizationMembership(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    organization_id: int = SQLField(foreign_key="organization.id", index=True)
    tenant_slug: str = SQLField(index=True)
    user_id: Optional[int] = SQLField(default=None, foreign_key="user.id", index=True)
    email: Optional[str] = SQLField(default=None, index=True)
    role: str = SQLField(default="analyst")
    status: str = SQLField(default="invited", index=True)
    invite_token: Optional[str] = SQLField(default=None, unique=True, index=True)
    invite_expires_at: Optional[datetime] = SQLField(default=None, index=True)
    invite_accepted_at: Optional[datetime] = SQLField(default=None)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    username: str = SQLField(index=True, unique=True)
    full_name: Optional[str] = None
    hashed_password: str
    tenant_id: str = SQLField(index=True)
    role: str = SQLField(default="admin")
    created_at: datetime = SQLField(default_factory=datetime.utcnow)


class UserSummary(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None


class OrganizationMembershipRead(BaseModel):
    id: int
    tenant_slug: str
    role: str
    status: str
    email: Optional[str]
    invite_token: Optional[str]
    invite_expires_at: Optional[datetime]
    invite_accepted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    organization: OrganizationBase
    user: Optional[UserSummary]


class MembershipAssignment(BaseModel):
    username: str
    role: str = Field("analyst", regex="^(analyst|admin)$")


class MembershipInviteRequest(BaseModel):
    email: str
    role: str = Field("analyst", regex="^(analyst|admin)$")


class InviteAcceptanceRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None


class TenantSwitchRequest(BaseModel):
    tenant_id: str


class PublicInviteRead(BaseModel):
    tenant_slug: str
    role: str
    status: str
    email: Optional[str]
    expires_at: Optional[datetime]
    expired: bool
    organization: OrganizationBase


class ContextSchemaDefinitionBase(BaseModel):
    field_key: str
    field_type: str = Field("string", regex="^(string|integer|boolean)$")
    required: bool = False


class ContextSchemaDefinition(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    tenant_id: str = SQLField(index=True)
    entity_type: str = SQLField(index=True)
    field_key: str = SQLField(index=True)
    field_type: str = SQLField(default="string")
    required: bool = SQLField(default=False)
    version: int = SQLField(default=1, index=True)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    is_active: bool = SQLField(default=True, index=True)


class ContextMutation(BaseModel):
    key: str
    value: Any


class ContextSchemaHistoryEntry(BaseModel):
    field_key: str
    field_type: str
    required: bool
    version: int
    created_at: datetime


class IncidentBase(BaseModel):
    title: str
    description: Optional[str] = None
    severity: str = Field("medium", regex="^(low|medium|high|critical)$")
    context: Dict[str, Any] = Field(default_factory=dict)


class Incident(SQLModel, IncidentBase, table=True):
    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = SQLField(index=True)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)
    context: Dict[str, Any] = SQLField(sa_column=Column(JSON), default_factory=dict)


class IndicatorBase(BaseModel):
    name: str
    indicator_type: str
    confidence: int = Field(50, ge=0, le=100)
    context: Dict[str, Any] = Field(default_factory=dict)


class Indicator(SQLModel, IndicatorBase, table=True):
    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = SQLField(index=True)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)
    context: Dict[str, Any] = SQLField(sa_column=Column(JSON), default_factory=dict)


class AutomationBase(BaseModel):
    name: str
    description: Optional[str] = None
    python_code: str


class Automation(SQLModel, AutomationBase, table=True):
    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = SQLField(index=True)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)


class AutomationExecutionRequest(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(0, ge=0, le=5)
    timeout_seconds: int = Field(60, ge=5, le=600)


class AutomationExecutionResult(BaseModel):
    success: bool
    logs: List[str] = Field(default_factory=list)
    output: Optional[Any] = None


class PlaybookNode(BaseModel):
    id: str
    automation_id: Optional[str] = None
    label: str
    x: float = 0.0
    y: float = 0.0


class PlaybookEdge(BaseModel):
    id: str
    source: str
    target: str
    condition: Optional[str] = None


class PlaybookBase(BaseModel):
    name: str
    description: Optional[str] = None
    nodes: List[PlaybookNode] = Field(default_factory=list)
    edges: List[PlaybookEdge] = Field(default_factory=list)


class Playbook(SQLModel, PlaybookBase, table=True):
    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = SQLField(index=True)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)
    nodes: List[PlaybookNode] = SQLField(
        sa_column=Column(JSON), default_factory=list
    )
    edges: List[PlaybookEdge] = SQLField(
        sa_column=Column(JSON), default_factory=list
    )


class PlaybookValidationResponse(BaseModel):
    valid: bool
    details: List[str] = Field(default_factory=list)


class PlaybookRunRequest(BaseModel):
    initial_context: Dict[str, Any] = Field(default_factory=dict)


class PlaybookRunResult(BaseModel):
    execution_log: List[str] = Field(default_factory=list)
    final_context: Dict[str, Any] = Field(default_factory=dict)


class AutomationRun(SQLModel, table=True):
    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    automation_id: str = SQLField(index=True)
    tenant_id: str = SQLField(index=True)
    status: str = SQLField(default="pending")
    logs: List[str] = SQLField(sa_column=Column(JSON), default_factory=list)
    output: Optional[Any] = SQLField(sa_column=Column(JSON), default=None)
    input_payload: Dict[str, Any] = SQLField(sa_column=Column(JSON), default_factory=dict)
    attempts: int = SQLField(default=0)
    max_retries: int = SQLField(default=0)
    timeout_seconds: int = SQLField(default=60)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    queue_latency_ms: Optional[int] = None
    last_error: Optional[str] = None
    timed_out: bool = SQLField(default=False)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)


class AutomationRunEvent(SQLModel, table=True):
    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    run_id: str = SQLField(foreign_key="automationrun.id", index=True)
    tenant_id: str = SQLField(index=True)
    event_type: str = SQLField(index=True)
    message: str = SQLField()
    payload: Dict[str, Any] = SQLField(sa_column=Column(JSON), default_factory=dict)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, index=True)


class AuditLog(SQLModel, table=True):
    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = SQLField(index=True)
    user_id: Optional[int] = SQLField(default=None, index=True)
    action: str
    entity_type: str
    entity_id: Optional[str] = SQLField(default=None, index=True)
    payload: Dict[str, Any] = SQLField(sa_column=Column(JSON), default_factory=dict)
    created_at: datetime = SQLField(default_factory=datetime.utcnow)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None


class AutomationRunBucket(BaseModel):
    bucket_start: datetime
    success: int
    failed: int
    running: int
    pending: int
    timeouts: int


class AutomationRunMetrics(BaseModel):
    window_hours: int
    from_ts: datetime
    to_ts: datetime
    total_runs: int
    success_count: int
    failed_count: int
    running_count: int
    pending_count: int
    timeout_count: int
    avg_duration_ms: Optional[float]
    avg_queue_latency_ms: Optional[float]
    per_hour: List[AutomationRunBucket]


class AutomationRunAggregate(BaseModel):
    automation_id: str
    automation_name: Optional[str]
    run_count: int
    success_count: int
    failure_count: int
    timeout_count: int
    retry_count: int
    avg_duration_ms: Optional[float]
    mean_time_between_retries_ms: Optional[float]
    last_run_at: Optional[datetime]


class AutomationRunAnalytics(BaseModel):
    window_hours: int
    from_ts: datetime
    to_ts: datetime
    total_runs: int
    total_failures: int
    total_timeouts: int
    automations: List[AutomationRunAggregate]


class AutomationRunnerStatus(BaseModel):
    queue_size: int
    processed_runs: int
    status: str
    active_run_id: Optional[str]
    last_heartbeat: Optional[datetime]
