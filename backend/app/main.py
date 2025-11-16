from __future__ import annotations

import csv
import json
import asyncio
from datetime import datetime, timedelta
from io import StringIO
from typing import List
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select

from .auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
    resolve_user_from_token,
    seed_default_user,
    verify_password,
)
from .automation_runner import enqueue_run, get_runner_status, start_runner
from .config import get_settings
from .database import engine, get_session, init_db
from .models import (
    AuditLog,
    Automation,
    AutomationBase,
    AutomationExecutionRequest,
    AutomationRun,
    AutomationRunEvent,
    AutomationRunMetrics,
    AutomationRunnerStatus,
    ContextMutation,
    ContextSchemaDefinition,
    ContextSchemaDefinitionBase,
    ContextSchemaHistoryEntry,
    Incident,
    IncidentBase,
    Indicator,
    IndicatorBase,
    InviteAcceptanceRequest,
    MembershipAssignment,
    MembershipInviteRequest,
    Organization,
    OrganizationBase,
    OrganizationMembership,
    OrganizationMembershipRead,
    Playbook,
    PlaybookBase,
    PlaybookRunRequest,
    PlaybookRunResult,
    PlaybookValidationResponse,
    PublicInviteRead,
    TenantSwitchRequest,
    Token,
    User,
    UserSummary,
)
from .services import (
    calculate_run_metrics,
    execute_automation_code,
    record_audit_log,
    record_run_event,
    run_playbook,
    validate_context,
    validate_context_mutation,
    validate_playbook,
)
from .realtime import publish_tenant_event, register_event_loop, stream_tenant_events

settings = get_settings()

app = FastAPI(title="SOAR Platform API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _membership_to_read(
    session: Session, membership: OrganizationMembership
) -> OrganizationMembershipRead:
    organization = session.get(Organization, membership.organization_id)
    org_payload = OrganizationBase(
        slug=organization.slug if organization else membership.tenant_slug,
        name=organization.name if organization else membership.tenant_slug,
    )
    user_payload = None
    if membership.user_id:
        member = session.get(User, membership.user_id)
        if member:
            user_payload = UserSummary(
                id=member.id,
                username=member.username,
                full_name=member.full_name,
            )
    return OrganizationMembershipRead(
        id=membership.id,
        tenant_slug=membership.tenant_slug,
        role=membership.role,
        status=membership.status,
        email=membership.email,
        invite_token=membership.invite_token,
        invite_expires_at=membership.invite_expires_at,
        invite_accepted_at=membership.invite_accepted_at,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
        organization=org_payload,
        user=user_payload,
    )


def _membership_to_public_invite(
    session: Session, membership: OrganizationMembership, expired: bool
) -> PublicInviteRead:
    organization = session.get(Organization, membership.organization_id)
    org_payload = OrganizationBase(
        slug=organization.slug if organization else membership.tenant_slug,
        name=organization.name if organization else membership.tenant_slug,
    )
    return PublicInviteRead(
        tenant_slug=membership.tenant_slug,
        role=membership.role,
        status=membership.status,
        email=membership.email,
        expires_at=membership.invite_expires_at,
        expired=expired,
        organization=org_payload,
    )


def _get_invite_by_token(session: Session, token: str) -> OrganizationMembership | None:
    statement = select(OrganizationMembership).where(OrganizationMembership.invite_token == token)
    return session.exec(statement).first()


def _mark_invite_expired_if_needed(
    membership: OrganizationMembership, session: Session
) -> bool:
    if (
        membership.status == "invited"
        and membership.invite_expires_at
        and membership.invite_expires_at < datetime.utcnow()
    ):
        membership.status = "expired"
        membership.updated_at = datetime.utcnow()
        session.add(membership)
        session.commit()
        session.refresh(membership)
        return True
    return membership.status == "expired"


def _complete_membership_invite(
    session: Session, membership: OrganizationMembership, *, user_id: int, email: str
) -> OrganizationMembership:
    membership.user_id = user_id
    membership.status = "active"
    membership.email = membership.email or email
    membership.invite_token = None
    membership.invite_accepted_at = datetime.utcnow()
    membership.updated_at = membership.invite_accepted_at
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


def _get_organization_by_slug(session: Session, slug: str) -> Organization | None:
    statement = select(Organization).where(Organization.slug == slug)
    return session.exec(statement).first()


def _emit_run_snapshot(run: AutomationRun) -> None:
    publish_tenant_event(run.tenant_id, "run_update", {"run": jsonable_encoder(run)})


@app.on_event("startup")
async def on_startup() -> None:
    register_event_loop(asyncio.get_running_loop())
    init_db()
    start_runner()
    with Session(engine) as session:
        seed_default_user(session)


@app.get("/api/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/api/ws/automation-events")
async def automation_events_websocket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return
    with Session(engine) as session:
        try:
            user = resolve_user_from_token(token, session)
        except HTTPException:
            await websocket.close(code=1008)
            return
        tenant_id = user.tenant_id
    await websocket.accept()
    try:
        async for event in stream_tenant_events(tenant_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return


@app.post("/api/auth/token", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> Token:
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": user.username})
    return Token(access_token=access_token)


# Organization management
@app.get("/api/organizations", response_model=List[Organization])
def list_organizations(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> List[Organization]:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can list organizations")
    statement = select(Organization)
    return session.exec(statement).all()


@app.post("/api/organizations", response_model=Organization, status_code=201)
def create_organization(
    payload: OrganizationBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Organization:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create organizations")
    existing = _get_organization_by_slug(session, payload.slug)
    if existing:
        raise HTTPException(status_code=400, detail="Organization already exists")
    organization = Organization(**payload.dict())
    session.add(organization)
    session.commit()
    session.refresh(organization)
    membership = OrganizationMembership(
        organization_id=organization.id,
        tenant_slug=organization.slug,
        user_id=user.id,
        role="admin" if user.role == "admin" else "analyst",
        status="active",
        email=user.username,
    )
    session.add(membership)
    session.commit()
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="organization.created",
        entity_type="organization",
        entity_id=organization.slug,
    )
    return organization


@app.get(
    "/api/organizations/{slug}/members",
    response_model=List[OrganizationMembershipRead],
)
def list_organization_members(
    slug: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[OrganizationMembershipRead]:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view members")
    organization = _get_organization_by_slug(session, slug)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    statement = (
        select(OrganizationMembership)
        .where(OrganizationMembership.organization_id == organization.id)
        .order_by(OrganizationMembership.created_at.desc())
    )
    memberships = session.exec(statement).all()
    return [_membership_to_read(session, membership) for membership in memberships]


@app.post(
    "/api/organizations/{slug}/members",
    response_model=OrganizationMembershipRead,
    status_code=201,
)
def assign_member_to_organization(
    slug: str,
    payload: MembershipAssignment,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> OrganizationMembershipRead:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage members")
    organization = _get_organization_by_slug(session, slug)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    target_user = session.exec(select(User).where(User.username == payload.username)).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    statement = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization.id,
        OrganizationMembership.user_id == target_user.id,
    )
    existing = session.exec(statement).first()
    if existing and existing.status == "active":
        raise HTTPException(status_code=400, detail="User already a member")
    membership = existing or OrganizationMembership(
        organization_id=organization.id,
        tenant_slug=organization.slug,
        email=target_user.username,
    )
    membership.user_id = target_user.id
    membership.role = payload.role
    membership.status = "active"
    membership.updated_at = datetime.utcnow()
    session.add(membership)
    session.commit()
    session.refresh(membership)
    record_audit_log(
        session,
        tenant_id=organization.slug,
        user_id=user.id,
        action="organization.member.assigned",
        entity_type="organization",
        entity_id=organization.slug,
        payload={"member": target_user.username, "role": payload.role},
    )
    return _membership_to_read(session, membership)


@app.post(
    "/api/organizations/{slug}/invites",
    response_model=OrganizationMembershipRead,
    status_code=201,
)
def invite_member(
    slug: str,
    payload: MembershipInviteRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> OrganizationMembershipRead:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can invite members")
    organization = _get_organization_by_slug(session, slug)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    existing = session.exec(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.email == payload.email,
            OrganizationMembership.status == "invited",
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Pending invite already exists")
    membership = OrganizationMembership(
        organization_id=organization.id,
        tenant_slug=organization.slug,
        email=payload.email,
        role=payload.role,
        status="invited",
        invite_token=str(uuid4()),
        invite_expires_at=datetime.utcnow() + timedelta(hours=settings.invite_expiry_hours),
    )
    session.add(membership)
    session.commit()
    session.refresh(membership)
    record_audit_log(
        session,
        tenant_id=organization.slug,
        user_id=user.id,
        action="organization.member.invited",
        entity_type="organization",
        entity_id=organization.slug,
        payload={"email": payload.email, "role": payload.role},
    )
    return _membership_to_read(session, membership)


@app.post(
    "/api/organization-invites/{token}/accept",
    response_model=OrganizationMembershipRead,
)
def accept_invite(
    token: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> OrganizationMembershipRead:
    membership = _get_invite_by_token(session, token)
    if not membership or membership.status not in {"invited", "expired"}:
        raise HTTPException(status_code=404, detail="Invite not found")
    expired = _mark_invite_expired_if_needed(membership, session)
    if expired:
        raise HTTPException(status_code=400, detail="Invite expired")
    membership = _complete_membership_invite(
        session, membership, user_id=user.id, email=user.username
    )
    record_audit_log(
        session,
        tenant_id=membership.tenant_slug,
        user_id=user.id,
        action="organization.member.accepted",
        entity_type="organization",
        entity_id=membership.tenant_slug,
        payload={"member": user.username},
    )
    return _membership_to_read(session, membership)


@app.get(
    "/api/public/invites/{token}",
    response_model=PublicInviteRead,
)
def get_public_invite(token: str, session: Session = Depends(get_session)) -> PublicInviteRead:
    membership = _get_invite_by_token(session, token)
    if not membership:
        raise HTTPException(status_code=404, detail="Invite not found")
    expired = _mark_invite_expired_if_needed(membership, session)
    return _membership_to_public_invite(session, membership, expired)


@app.post(
    "/api/public/invites/{token}/accept",
    response_model=OrganizationMembershipRead,
    status_code=201,
)
def accept_public_invite(
    token: str,
    payload: InviteAcceptanceRequest,
    session: Session = Depends(get_session),
) -> OrganizationMembershipRead:
    membership = _get_invite_by_token(session, token)
    if not membership or membership.status not in {"invited", "expired"}:
        raise HTTPException(status_code=404, detail="Invite not found")
    expired = _mark_invite_expired_if_needed(membership, session)
    if expired:
        raise HTTPException(status_code=400, detail="Invite expired")
    statement = select(User).where(User.username == payload.username)
    existing_user = session.exec(statement).first()
    if existing_user:
        if not verify_password(payload.password, existing_user.hashed_password):
            raise HTTPException(status_code=400, detail="Invalid credentials")
        user = existing_user
    else:
        user = User(
            username=payload.username,
            full_name=payload.full_name,
            hashed_password=get_password_hash(payload.password),
            tenant_id=membership.tenant_slug,
            role=membership.role,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    membership = _complete_membership_invite(
        session, membership, user_id=user.id, email=payload.username
    )
    record_audit_log(
        session,
        tenant_id=membership.tenant_slug,
        user_id=user.id,
        action="organization.member.accepted",
        entity_type="organization",
        entity_id=membership.tenant_slug,
        payload={"member": user.username, "via": "public"},
    )
    return _membership_to_read(session, membership)


@app.get("/api/me/memberships", response_model=List[OrganizationMembershipRead])
def list_my_memberships(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> List[OrganizationMembershipRead]:
    statement = select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)
    memberships = session.exec(statement).all()
    return [_membership_to_read(session, membership) for membership in memberships]


@app.post("/api/me/tenant")
def switch_tenant(
    payload: TenantSwitchRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    membership = session.exec(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.tenant_slug == payload.tenant_id,
            OrganizationMembership.status == "active",
        )
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Membership not found")
    user.tenant_id = membership.tenant_slug
    session.add(user)
    session.commit()
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="user.tenant.switched",
        entity_type="user",
        entity_id=str(user.id),
        payload={"tenant": payload.tenant_id},
    )
    return {"tenant_id": user.tenant_id}


# Context schema endpoints
@app.get(
    "/api/context-schemas/{entity_type}",
    response_model=List[ContextSchemaDefinition],
)
def list_context_schema(
    entity_type: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[ContextSchemaDefinition]:
    statement = (
        select(ContextSchemaDefinition)
        .where(
            ContextSchemaDefinition.tenant_id == user.tenant_id,
            ContextSchemaDefinition.entity_type == entity_type,
            ContextSchemaDefinition.is_active.is_(True),
        )
        .order_by(ContextSchemaDefinition.field_key, ContextSchemaDefinition.version)
    )
    latest: dict[str, ContextSchemaDefinition] = {}
    for definition in session.exec(statement).all():
        if (
            definition.field_key not in latest
            or latest[definition.field_key].version <= definition.version
        ):
            latest[definition.field_key] = definition
    return sorted(latest.values(), key=lambda definition: definition.field_key)


@app.post(
    "/api/context-schemas/{entity_type}",
    response_model=ContextSchemaDefinition,
    status_code=201,
)
def upsert_context_schema(
    entity_type: str,
    payload: ContextSchemaDefinitionBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ContextSchemaDefinition:
    statement = (
        select(ContextSchemaDefinition)
        .where(
            ContextSchemaDefinition.tenant_id == user.tenant_id,
            ContextSchemaDefinition.entity_type == entity_type,
            ContextSchemaDefinition.field_key == payload.field_key,
        )
        .order_by(ContextSchemaDefinition.version.desc())
    )
    latest = session.exec(statement).first()
    next_version = (latest.version + 1) if latest else 1
    definition = ContextSchemaDefinition(
        tenant_id=user.tenant_id,
        entity_type=entity_type,
        field_key=payload.field_key,
        field_type=payload.field_type,
        required=payload.required,
        version=next_version,
        is_active=True,
    )
    session.add(definition)
    session.commit()
    session.refresh(definition)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="schema.updated",
        entity_type=entity_type,
        entity_id=payload.field_key,
        payload={"version": definition.version},
    )
    return definition


@app.delete(
    "/api/context-schemas/{entity_type}/{field_key}",
    status_code=204,
)
def delete_context_field(
    entity_type: str,
    field_key: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    statement = (
        select(ContextSchemaDefinition)
        .where(
            ContextSchemaDefinition.tenant_id == user.tenant_id,
            ContextSchemaDefinition.entity_type == entity_type,
            ContextSchemaDefinition.field_key == field_key,
        )
        .order_by(ContextSchemaDefinition.version.desc())
    )
    latest = session.exec(statement).first()
    if not latest or not latest.is_active:
        raise HTTPException(status_code=404, detail="Field not found")
    definition = ContextSchemaDefinition(
        tenant_id=user.tenant_id,
        entity_type=entity_type,
        field_key=field_key,
        field_type=latest.field_type,
        required=latest.required,
        version=latest.version + 1,
        is_active=False,
    )
    session.add(definition)
    session.commit()
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="schema.deleted",
        entity_type=entity_type,
        entity_id=field_key,
        payload={"version": definition.version},
    )


@app.get(
    "/api/context-schemas/{entity_type}/{field_key}/history",
    response_model=List[ContextSchemaHistoryEntry],
)
def get_context_field_history(
    entity_type: str,
    field_key: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[ContextSchemaHistoryEntry]:
    statement = (
        select(ContextSchemaDefinition)
        .where(
            ContextSchemaDefinition.tenant_id == user.tenant_id,
            ContextSchemaDefinition.entity_type == entity_type,
            ContextSchemaDefinition.field_key == field_key,
        )
        .order_by(ContextSchemaDefinition.version.desc())
    )
    definitions = session.exec(statement).all()
    if not definitions:
        raise HTTPException(status_code=404, detail="Field not found")
    return [
        ContextSchemaHistoryEntry(
            field_key=item.field_key,
            field_type=item.field_type,
            required=item.required,
            version=item.version,
            created_at=item.created_at,
        )
        for item in definitions
    ]


# Incident endpoints
@app.get("/api/incidents", response_model=List[Incident])
def list_incidents(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> List[Incident]:
    statement = select(Incident).where(Incident.tenant_id == user.tenant_id)
    return session.exec(statement).all()


@app.post("/api/incidents", response_model=Incident, status_code=201)
def create_incident(
    payload: IncidentBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Incident:
    normalized_context = validate_context(session, user.tenant_id, "incidents", payload.context)
    incident = Incident(
        **payload.dict(exclude={"context"}),
        context=normalized_context,
        tenant_id=user.tenant_id,
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="incident.created",
        entity_type="incident",
        entity_id=incident.id,
        payload={"title": incident.title},
    )
    return incident


@app.get("/api/incidents/{incident_id}", response_model=Incident)
def get_incident(
    incident_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Incident:
    incident = session.get(Incident, incident_id)
    if not incident or incident.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.put("/api/incidents/{incident_id}", response_model=Incident)
def update_incident(
    incident_id: str,
    payload: IncidentBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Incident:
    incident = session.get(Incident, incident_id)
    if not incident or incident.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.title = payload.title
    incident.description = payload.description
    incident.severity = payload.severity
    incident.context = validate_context(session, user.tenant_id, "incidents", payload.context)
    incident.updated_at = datetime.utcnow()
    session.add(incident)
    session.commit()
    session.refresh(incident)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="incident.updated",
        entity_type="incident",
        entity_id=incident.id,
    )
    return incident


@app.delete("/api/incidents/{incident_id}", status_code=204)
def delete_incident(
    incident_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    incident = session.get(Incident, incident_id)
    if not incident or incident.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Incident not found")
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="incident.deleted",
        entity_type="incident",
        entity_id=incident.id,
    )
    session.delete(incident)
    session.commit()


@app.post("/api/incidents/{incident_id}/context/fields", response_model=Incident)
def add_incident_context_field(
    incident_id: str,
    mutation: ContextMutation,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Incident:
    incident = session.get(Incident, incident_id)
    if not incident or incident.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.context[mutation.key] = validate_context_mutation(
        session, user.tenant_id, "incidents", mutation.key, mutation.value
    )
    incident.updated_at = datetime.utcnow()
    session.add(incident)
    session.commit()
    session.refresh(incident)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="incident.context.added",
        entity_type="incident",
        entity_id=incident.id,
        payload={"field": mutation.key},
    )
    return incident


@app.delete("/api/incidents/{incident_id}/context/fields/{field_key}", response_model=Incident)
def delete_incident_context_field(
    incident_id: str,
    field_key: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Incident:
    incident = session.get(Incident, incident_id)
    if not incident or incident.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.context.pop(field_key, None)
    incident.updated_at = datetime.utcnow()
    session.add(incident)
    session.commit()
    session.refresh(incident)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="incident.context.removed",
        entity_type="incident",
        entity_id=incident.id,
        payload={"field": field_key},
    )
    return incident


# Indicator endpoints
@app.get("/api/indicators", response_model=List[Indicator])
def list_indicators(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> List[Indicator]:
    statement = select(Indicator).where(Indicator.tenant_id == user.tenant_id)
    return session.exec(statement).all()


@app.post("/api/indicators", response_model=Indicator, status_code=201)
def create_indicator(
    payload: IndicatorBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Indicator:
    normalized_context = validate_context(session, user.tenant_id, "indicators", payload.context)
    indicator = Indicator(
        **payload.dict(exclude={"context"}),
        context=normalized_context,
        tenant_id=user.tenant_id,
    )
    session.add(indicator)
    session.commit()
    session.refresh(indicator)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="indicator.created",
        entity_type="indicator",
        entity_id=indicator.id,
    )
    return indicator


@app.put("/api/indicators/{indicator_id}", response_model=Indicator)
def update_indicator(
    indicator_id: str,
    payload: IndicatorBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Indicator:
    indicator = session.get(Indicator, indicator_id)
    if not indicator or indicator.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Indicator not found")
    indicator.name = payload.name
    indicator.indicator_type = payload.indicator_type
    indicator.confidence = payload.confidence
    indicator.context = validate_context(session, user.tenant_id, "indicators", payload.context)
    indicator.updated_at = datetime.utcnow()
    session.add(indicator)
    session.commit()
    session.refresh(indicator)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="indicator.updated",
        entity_type="indicator",
        entity_id=indicator.id,
    )
    return indicator


@app.delete("/api/indicators/{indicator_id}", status_code=204)
def delete_indicator(
    indicator_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    indicator = session.get(Indicator, indicator_id)
    if not indicator or indicator.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Indicator not found")
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="indicator.deleted",
        entity_type="indicator",
        entity_id=indicator.id,
    )
    session.delete(indicator)
    session.commit()


@app.post("/api/indicators/{indicator_id}/context/fields", response_model=Indicator)
def add_indicator_context_field(
    indicator_id: str,
    mutation: ContextMutation,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Indicator:
    indicator = session.get(Indicator, indicator_id)
    if not indicator or indicator.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Indicator not found")
    indicator.context[mutation.key] = validate_context_mutation(
        session, user.tenant_id, "indicators", mutation.key, mutation.value
    )
    indicator.updated_at = datetime.utcnow()
    session.add(indicator)
    session.commit()
    session.refresh(indicator)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="indicator.context.added",
        entity_type="indicator",
        entity_id=indicator.id,
        payload={"field": mutation.key},
    )
    return indicator


@app.delete("/api/indicators/{indicator_id}/context/fields/{field_key}", response_model=Indicator)
def delete_indicator_context_field(
    indicator_id: str,
    field_key: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Indicator:
    indicator = session.get(Indicator, indicator_id)
    if not indicator or indicator.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Indicator not found")
    indicator.context.pop(field_key, None)
    indicator.updated_at = datetime.utcnow()
    session.add(indicator)
    session.commit()
    session.refresh(indicator)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="indicator.context.removed",
        entity_type="indicator",
        entity_id=indicator.id,
        payload={"field": field_key},
    )
    return indicator


# Automation endpoints
@app.get("/api/automations", response_model=List[Automation])
def list_automations(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> List[Automation]:
    statement = select(Automation).where(Automation.tenant_id == user.tenant_id)
    return session.exec(statement).all()


@app.post("/api/automations", response_model=Automation, status_code=201)
def create_automation(
    payload: AutomationBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Automation:
    automation = Automation(**payload.dict(), tenant_id=user.tenant_id)
    session.add(automation)
    session.commit()
    session.refresh(automation)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="automation.created",
        entity_type="automation",
        entity_id=automation.id,
    )
    return automation


@app.put("/api/automations/{automation_id}", response_model=Automation)
def update_automation(
    automation_id: str,
    payload: AutomationBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Automation:
    automation = session.get(Automation, automation_id)
    if not automation or automation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Automation not found")
    automation.name = payload.name
    automation.description = payload.description
    automation.python_code = payload.python_code
    automation.updated_at = datetime.utcnow()
    session.add(automation)
    session.commit()
    session.refresh(automation)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="automation.updated",
        entity_type="automation",
        entity_id=automation.id,
    )
    return automation


@app.delete("/api/automations/{automation_id}", status_code=204)
def delete_automation(
    automation_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    automation = session.get(Automation, automation_id)
    if not automation or automation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Automation not found")
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="automation.deleted",
        entity_type="automation",
        entity_id=automation.id,
    )
    session.delete(automation)
    session.commit()


@app.post("/api/automations/{automation_id}/runs", response_model=AutomationRun, status_code=202)
def queue_automation_run(
    automation_id: str,
    payload: AutomationExecutionRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AutomationRun:
    automation = session.get(Automation, automation_id)
    if not automation or automation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Automation not found")
    run = AutomationRun(
        automation_id=automation_id,
        tenant_id=user.tenant_id,
        input_payload=payload.inputs,
        status="pending",
        max_retries=payload.max_retries,
        timeout_seconds=payload.timeout_seconds,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    _emit_run_snapshot(run)
    record_run_event(
        session,
        run=run,
        event_type="queued",
        message="Çalışma kuyruğa alındı",
        payload={
            "automation_id": automation_id,
            "max_retries": run.max_retries,
            "timeout_seconds": run.timeout_seconds,
        },
    )
    enqueue_run(run.id, user.tenant_id)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="automation.run.queued",
        entity_type="automation",
        entity_id=automation.id,
        payload={"run_id": run.id},
    )
    return run


@app.get("/api/automations/{automation_id}/runs", response_model=List[AutomationRun])
def list_automation_runs(
    automation_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[AutomationRun]:
    automation = session.get(Automation, automation_id)
    if not automation or automation.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Automation not found")
    statement = (
        select(AutomationRun)
        .where(
            AutomationRun.tenant_id == user.tenant_id,
            AutomationRun.automation_id == automation_id,
        )
        .order_by(AutomationRun.created_at.desc())
    )
    return session.exec(statement).all()


@app.get("/api/automation-runs/{run_id}", response_model=AutomationRun)
def get_automation_run(
    run_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AutomationRun:
    run = session.get(AutomationRun, run_id)
    if not run or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/automation-runs/{run_id}/events", response_model=List[AutomationRunEvent])
def get_automation_run_events(
    run_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[AutomationRunEvent]:
    run = session.get(AutomationRun, run_id)
    if not run or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Run not found")
    statement = (
        select(AutomationRunEvent)
        .where(AutomationRunEvent.run_id == run_id)
        .order_by(AutomationRunEvent.created_at.asc())
    )
    return session.exec(statement).all()


@app.get(
    "/api/automation-runs/metrics",
    response_model=AutomationRunMetrics,
)
def get_automation_run_metrics(
    window_hours: int = Query(24, ge=1, le=168),
    automation_id: str | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AutomationRunMetrics:
    now = datetime.utcnow()
    since = now - timedelta(hours=window_hours)
    statement = select(AutomationRun).where(
        AutomationRun.tenant_id == user.tenant_id,
        AutomationRun.created_at >= since,
    )
    if automation_id:
        statement = statement.where(AutomationRun.automation_id == automation_id)
    runs = session.exec(statement).all()
    return calculate_run_metrics(runs, window_hours=window_hours, since=since, until=now)


@app.get(
    "/api/automation-runner/status",
    response_model=AutomationRunnerStatus,
)
def automation_runner_status(user: User = Depends(get_current_user)) -> AutomationRunnerStatus:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view runner status")
    data = get_runner_status()
    return AutomationRunnerStatus(**data)


@app.post(
    "/api/automation-runs/{run_id}/requeue",
    response_model=AutomationRun,
)
def requeue_automation_run(
    run_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AutomationRun:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can requeue runs")
    run = session.get(AutomationRun, run_id)
    if not run or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "failed":
        raise HTTPException(status_code=400, detail="Only failed runs can be requeued")
    run.status = "pending"
    run.attempts = 0
    run.logs = (run.logs or []) + ["Yönetici tarafından yeniden kuyruğa alındı"]
    run.last_error = None
    run.queue_latency_ms = None
    run.duration_ms = None
    run.started_at = None
    run.finished_at = None
    run.timed_out = False
    run.updated_at = datetime.utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    _emit_run_snapshot(run)
    record_run_event(
        session,
        run=run,
        event_type="manual_requeue",
        message="Yönetici tarafından yeniden kuyruğa alındı",
        payload={"automation_id": run.automation_id},
    )
    enqueue_run(run.id, user.tenant_id)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="automation.run.requeued",
        entity_type="automation_run",
        entity_id=run.id,
        payload={"automation_id": run.automation_id},
    )
    return run


@app.get("/api/audit-logs", response_model=List[AuditLog])
def list_audit_logs(
    action: str | None = None,
    entity_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(200, ge=10, le=1000),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[AuditLog]:
    statement = select(AuditLog).where(AuditLog.tenant_id == user.tenant_id)
    if action:
        statement = statement.where(AuditLog.action == action)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if start:
        statement = statement.where(AuditLog.created_at >= start)
    if end:
        statement = statement.where(AuditLog.created_at <= end)
    statement = statement.order_by(AuditLog.created_at.desc()).limit(limit)
    return session.exec(statement).all()


@app.get("/api/audit-logs/export")
def export_audit_logs(
    action: str | None = None,
    entity_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    statement = select(AuditLog).where(AuditLog.tenant_id == user.tenant_id)
    if action:
        statement = statement.where(AuditLog.action == action)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if start:
        statement = statement.where(AuditLog.created_at >= start)
    if end:
        statement = statement.where(AuditLog.created_at <= end)
    logs = session.exec(statement.order_by(AuditLog.created_at.desc())).all()
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "action", "entity_type", "entity_id", "created_at", "payload"])
    for entry in logs:
        writer.writerow(
            [
                entry.id,
                entry.action,
                entry.entity_type,
                entry.entity_id or "",
                entry.created_at.isoformat(),
                json.dumps(entry.payload or {}),
            ]
        )
    content = buffer.getvalue()
    buffer.close()
    filename = f"audit_logs_{user.tenant_id}.csv"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# Playbook endpoints
@app.get("/api/playbooks", response_model=List[Playbook])
def list_playbooks(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> List[Playbook]:
    statement = select(Playbook).where(Playbook.tenant_id == user.tenant_id)
    return session.exec(statement).all()


@app.post("/api/playbooks", response_model=Playbook, status_code=201)
def create_playbook(
    payload: PlaybookBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Playbook:
    playbook = Playbook(**payload.dict(), tenant_id=user.tenant_id)
    session.add(playbook)
    session.commit()
    session.refresh(playbook)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="playbook.created",
        entity_type="playbook",
        entity_id=playbook.id,
    )
    return playbook


@app.put("/api/playbooks/{playbook_id}", response_model=Playbook)
def update_playbook(
    playbook_id: str,
    payload: PlaybookBase,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Playbook:
    playbook = session.get(Playbook, playbook_id)
    if not playbook or playbook.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Playbook not found")
    playbook.name = payload.name
    playbook.description = payload.description
    playbook.nodes = payload.nodes
    playbook.edges = payload.edges
    playbook.updated_at = datetime.utcnow()
    session.add(playbook)
    session.commit()
    session.refresh(playbook)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="playbook.updated",
        entity_type="playbook",
        entity_id=playbook.id,
    )
    return playbook


@app.delete("/api/playbooks/{playbook_id}", status_code=204)
def delete_playbook(
    playbook_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    playbook = session.get(Playbook, playbook_id)
    if not playbook or playbook.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Playbook not found")
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="playbook.deleted",
        entity_type="playbook",
        entity_id=playbook.id,
    )
    session.delete(playbook)
    session.commit()


@app.post("/api/playbooks/{playbook_id}/validate", response_model=PlaybookValidationResponse)
def validate_playbook_endpoint(
    playbook_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PlaybookValidationResponse:
    playbook = session.get(Playbook, playbook_id)
    if not playbook or playbook.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Playbook not found")
    response = validate_playbook(playbook)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="playbook.validated",
        entity_type="playbook",
        entity_id=playbook.id,
        payload={"valid": response.valid},
    )
    return response


@app.post("/api/playbooks/{playbook_id}/run", response_model=PlaybookRunResult)
def run_playbook_endpoint(
    playbook_id: str,
    payload: PlaybookRunRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PlaybookRunResult:
    playbook = session.get(Playbook, playbook_id)
    if not playbook or playbook.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Playbook not found")
    automation_ids = {node.automation_id for node in playbook.nodes if node.automation_id}
    automations: dict[str, Automation] = {}
    if automation_ids:
        statement = select(Automation).where(
            Automation.tenant_id == user.tenant_id,
            Automation.id.in_(automation_ids),
        )
        automations = {automation.id: automation for automation in session.exec(statement).all()}
    result = run_playbook(playbook, automations, payload.initial_context)
    record_audit_log(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="playbook.ran",
        entity_type="playbook",
        entity_id=playbook.id,
        payload={"log_entries": len(result.execution_log)},
    )
    return result
