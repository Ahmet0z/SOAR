from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from .config import get_settings
from .database import get_session
from .models import Organization, OrganizationMembership, TokenData, User

settings = get_settings()
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def authenticate_user(session: Session, username: str, password: str) -> Optional[User]:
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError as exc:  # pragma: no cover - sanity guard
        raise credentials_exception from exc

    statement = select(User).where(User.username == token_data.username)
    user = session.exec(statement).first()
    if user is None:
        raise credentials_exception
    return user


def seed_default_user(session: Session) -> None:
    statement = select(User).where(User.username == settings.default_admin_username)
    user = session.exec(statement).first()
    if user:
        return
    org_statement = select(Organization).where(Organization.slug == settings.default_tenant_slug)
    organization = session.exec(org_statement).first()
    if not organization:
        organization = Organization(slug=settings.default_tenant_slug, name=settings.default_tenant_name)
        session.add(organization)
        session.commit()
        session.refresh(organization)
    admin = User(
        username=settings.default_admin_username,
        full_name="Default Admin",
        hashed_password=get_password_hash(settings.default_admin_password),
        tenant_id=organization.slug,
        role="admin",
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    membership = OrganizationMembership(
        organization_id=organization.id,
        tenant_slug=organization.slug,
        user_id=admin.id,
        role="admin",
        status="active",
        email=None,
    )
    session.add(membership)
    session.commit()
