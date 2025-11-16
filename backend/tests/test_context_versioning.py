from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.models import ContextSchemaDefinition
from app.services import validate_context


def setup_module(_: object) -> None:
    global engine
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)


def test_validate_context_uses_latest_active_version():
    with Session(engine) as session:
        session.add(
            ContextSchemaDefinition(
                tenant_id="t1",
                entity_type="incidents",
                field_key="priority",
                field_type="string",
                required=True,
                version=1,
            )
        )
        session.add(
            ContextSchemaDefinition(
                tenant_id="t1",
                entity_type="incidents",
                field_key="priority",
                field_type="integer",
                required=True,
                version=2,
            )
        )
        session.add(
            ContextSchemaDefinition(
                tenant_id="t1",
                entity_type="incidents",
                field_key="priority",
                field_type="integer",
                required=True,
                version=3,
                is_active=False,
            )
        )
        session.commit()
        normalized = validate_context(session, "t1", "incidents", {"priority": "7"})
        assert normalized["priority"] == 7


def test_missing_required_field_raises_http_exception():
    with Session(engine) as session:
        session.add(
            ContextSchemaDefinition(
                tenant_id="t1",
                entity_type="indicators",
                field_key="source",
                field_type="string",
                required=True,
                version=1,
            )
        )
        session.commit()
        try:
            validate_context(session, "t1", "indicators", {})
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "Missing required" in exc.detail
        else:
            raise AssertionError("HTTPException was not raised for missing field")
