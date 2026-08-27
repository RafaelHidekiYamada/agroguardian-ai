from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import models
from .database import get_db

SECRET_KEY = os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

ROLE_ORDER = ["ADMIN", "SOMPO", "GESTOR", "OPERADOR", "ANALISTA", "LEITURA"]

DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "ADMIN": {
        "users.view",
        "users.create",
        "users.edit",
        "users.delete",
        "clients.view",
        "clients.create",
        "clients.edit",
        "clients.delete",
        "farms.view",
        "farms.create",
        "farms.edit",
        "farms.delete",
        "equipments.view",
        "equipments.create",
        "equipments.edit",
        "equipments.delete",
        "telemetry.view",
        "alerts.view",
        "alerts.manage",
        "risk.view",
        "risk.predict",
        "risk.simulate",
        "reports.view",
        "reports.export",
        "audit.view",
        "model.view",
        "model.manage",
        "settings.manage",
        "iot.devices.view",
        "iot.devices.manage",
    },
    "SOMPO": {
        "clients.view",
        "equipments.view",
        "telemetry.view",
        "alerts.view",
        "risk.view",
        "reports.view",
        "reports.export",
        "audit.view",
        "model.view",
        "iot.devices.view",
    },
    "GESTOR": {
        "farms.view",
        "farms.create",
        "farms.edit",
        "equipments.view",
        "equipments.create",
        "equipments.edit",
        "telemetry.view",
        "alerts.view",
        "alerts.manage",
        "risk.view",
        "risk.predict",
        "risk.simulate",
        "reports.view",
        "iot.devices.view",
        "iot.devices.manage",
    },
    "OPERADOR": {
        "equipments.view",
        "telemetry.view",
        "alerts.view",
        "risk.view",
        "risk.predict",
    },
    "ANALISTA": {
        "equipments.view",
        "telemetry.view",
        "alerts.view",
        "risk.view",
        "risk.predict",
        "risk.simulate",
        "reports.view",
        "reports.export",
        "model.view",
        "iot.devices.view",
    },
    "LEITURA": {
        "clients.view",
        "farms.view",
        "equipments.view",
        "telemetry.view",
        "alerts.view",
        "risk.view",
        "reports.view",
    },
}

ALL_PERMISSIONS = sorted({item for values in DEFAULT_ROLE_PERMISSIONS.values() for item in values})


def normalize_role(role: str | None) -> str:
    value = str(role or "LEITURA").strip().upper()
    if value == "ADMINISTRADOR":
        return "ADMIN"
    return value if value in DEFAULT_ROLE_PERMISSIONS else "LEITURA"


def hash_password(password: str) -> str:
    secret = password.encode("utf-8")[:72]
    return bcrypt.hashpw(secret, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        return bcrypt.checkpw(plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8"))
    return pwd_context.verify(plain_password, hashed_password)


def hash_api_key(api_key: str) -> str:
    return hash_password(api_key)


def verify_api_key(plain_api_key: str, api_key_hash: str) -> bool:
    return verify_password(plain_api_key, api_key_hash)


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _legacy_user_adapter(legacy_user):
    class LegacyUser:
        id = getattr(legacy_user, "id", None)
        username = legacy_user.username
        name = legacy_user.full_name
        full_name = legacy_user.full_name
        email = legacy_user.email
        role = normalize_role(legacy_user.role)
        roles = []
        is_active = legacy_user.is_active
        status = "active" if legacy_user.is_active else "inactive"
        last_login_at = legacy_user.last_login_at
        created_at = legacy_user.created_at
        updated_at = legacy_user.created_at
        password_hash = legacy_user.hashed_password
        hashed_password = legacy_user.hashed_password
        permission_overrides = []
        access_scopes = []

    return LegacyUser()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais invalidas",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        legacy = (
            db.query(models.UserAccount)
            .filter(models.UserAccount.username == username)
            .first()
        )
        if legacy is not None:
            user = _legacy_user_adapter(legacy)

    if user is None or not user.is_active:
        raise credentials_exception

    return user


def get_user_roles(user) -> list[str]:
    roles = [normalize_role(getattr(role, "name", None)) for role in getattr(user, "roles", [])]
    if not roles and getattr(user, "role", None):
        roles = [normalize_role(getattr(user, "role"))]
    return roles or ["LEITURA"]


def get_primary_role(user) -> str:
    roles = get_user_roles(user)
    order = {role: index for index, role in enumerate(ROLE_ORDER)}
    return sorted(roles, key=lambda value: order.get(value, 999))[0]


def get_user_permissions(user) -> set[str]:
    effective: set[str] = set()
    for role_name in get_user_roles(user):
        effective.update(DEFAULT_ROLE_PERMISSIONS.get(normalize_role(role_name), set()))

    for override in getattr(user, "permission_overrides", []) or []:
        permission = getattr(override, "permission", None)
        code = getattr(permission, "code", None)
        if not code:
            continue
        if getattr(override, "allowed", True):
            effective.add(code)
        else:
            effective.discard(code)

    return effective


def require_roles(*allowed_roles: str):
    def dependency(current_user=Depends(get_current_user)):
        allowed = {normalize_role(role) for role in allowed_roles}
        if set(get_user_roles(current_user)).isdisjoint(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voce nao tem permissao para acessar este recurso.",
            )
        return current_user

    return dependency


def require_permission(permission_code: str):
    def dependency(current_user=Depends(get_current_user)):
        if permission_code not in get_user_permissions(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voce nao tem permissao para acessar este recurso.",
            )
        return current_user

    return dependency


def authenticate_user(db: Session, username_or_email: str, password: str):
    user = (
        db.query(models.User)
        .filter(
            or_(
                models.User.username == username_or_email,
                models.User.email == username_or_email,
            )
        )
        .first()
    )
    if user and verify_password(password, user.password_hash):
        return user

    legacy = (
        db.query(models.UserAccount)
        .filter(models.UserAccount.username == username_or_email)
        .first()
    )
    if legacy and verify_password(password, legacy.hashed_password):
        return _legacy_user_adapter(legacy)

    return None
