from __future__ import annotations

from pathlib import Path
from typing import Iterator

from alembic import command
from alembic.config import Config
from sqlmodel import Session, create_engine

from .config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


def init_db() -> None:
    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
