"""Autenticación con sesión persistente y autorización centralizada.

La identidad ya no se toma de la cabecera ``X-Actor-Username``: esa cabecera
podía suplantar a cualquier usuario. El cliente recibe un token firmado
(HMAC-SHA256) que envía en ``Authorization: Bearer <token>`` y que se valida en
cada petición, comprobando también que la cuenta siga activa y pertenezca al
parqueadero. El token se guarda en ``sessionStorage`` en Angular.

El secreto de firma se lee de ``SESSION_SECRET`` (obligatorio en despliegue).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Employee, Role, UserAccount, UserActivity, UserRole
from .rbac import PAGE_PERMISSIONS, permissions_for_roles
from .security import hash_password, verify_password

TOKEN_TTL_HOURS = 8
MAX_TOKEN_AGE = 24 * 60 * 60
SESSION_SECRET_ENV = "SESSION_SECRET"

#: Permite a ``resolve_parking_lot`` y a la bitácora saber quién actúa sin
#: modificar la firma de decenas de endpoints existentes.
current_principal: ContextVar["Principal | None"] = ContextVar("current_principal", default=None)


def _secret() -> bytes:
    value = os.getenv(SESSION_SECRET_ENV, "").strip()
    if len(value) < 32:
        raise RuntimeError(
            "SESSION_SECRET no está definido o es demasiado corto. "
            "Genera uno con: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return value.encode("utf-8")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class Principal:
    user_id: int
    parking_lot_id: int
    employee_id: int
    username: str
    display_name: str
    role_codes: tuple[str, ...]
    permissions: frozenset[str]
    must_change_password: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "parking_lot_id": self.parking_lot_id,
            "employee_id": self.employee_id,
            "role_codes": list(self.role_codes),
            "permissions": sorted(self.permissions),
            "must_change_password": self.must_change_password,
        }


def build_principal(db: Session, user: UserAccount) -> Principal:
    codes = tuple(
        db.execute(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
            .order_by(Role.sort, Role.id)
        ).scalars().all()
    )
    employee = db.get(Employee, user.employee_id)
    return Principal(
        user_id=user.id,
        parking_lot_id=user.parking_lot_id,
        employee_id=user.employee_id,
        username=user.username,
        display_name=(employee.full_name if employee else user.username)[:60],
        role_codes=codes,
        permissions=permissions_for_roles(codes),
        must_change_password=bool(getattr(user, "must_change_password", False)),
    )


def create_token(principal: Principal) -> str:
    """Token firmado, sin datos sensibles. Caduca en ``TOKEN_TTL_HOURS``."""
    issued = datetime.now()
    payload = {
        "sub": principal.username,
        "uid": principal.user_id,
        "lot": principal.parking_lot_id,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(hours=TOKEN_TTL_HOURS)).timestamp()),
        "nonce": os.urandom(8).hex(),
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64encode(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
    except (ValueError, AttributeError):
        return None
    expected = _b64encode(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, UnicodeDecodeError):
        return None
    issued = payload.get("iat")
    expires = payload.get("exp")
    if not isinstance(issued, int) or not isinstance(expires, int):
        return None
    now = int(datetime.now().timestamp())
    if expires <= now or issued > now + 60 or now - issued > MAX_TOKEN_AGE:
        return None
    return payload


AUTH_FREE_PATHS = frozenset({"/api/auth/login"})


def authenticate(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Principal:
    """Valida el token en cada petición y devuelve el principal vigente."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Inicia sesión para continuar.")
    payload = decode_token(token.strip())
    if not payload:
        raise HTTPException(401, "Tu sesión no es válida o ha caducado. Inicia sesión de nuevo.")
    user = db.get(UserAccount, payload.get("uid"))
    if not user or user.username != payload.get("sub"):
        raise HTTPException(401, "Tu sesión ya no corresponde a una cuenta vigente.")
    if user.parking_lot_id != payload.get("lot"):
        raise HTTPException(403, "La cuenta autenticada no pertenece a este parqueadero.")
    if not user.active:
        raise HTTPException(403, "Tu cuenta está desactivada. Contacta al administrador.")
    # `attach_session_context` ya validó este mismo token y construyó el
    # principal. Se reutiliza solo cuando coincide exactamente con la petición;
    # en cualquier otro caso se recalcula. Las comprobaciones de token, cuenta,
    # parqueadero y estado siguen ejecutándose aquí (sin relajar la seguridad).
    principal = getattr(request.state, "principal", None)
    cached_token = getattr(request.state, "auth_token", None)
    if (principal is None or cached_token != token.strip()
            or principal.user_id != user.id
            or principal.username != user.username
            or principal.parking_lot_id != user.parking_lot_id):
        principal = build_principal(db, user)
    current_principal.set(principal)
    if principal.must_change_password and request.url.path not in {
        "/api/auth/change-password",
        "/api/auth/me",
        "/api/auth/logout",
    }:
        raise HTTPException(403, "Debes cambiar tu contraseña temporal antes de continuar.")
    return principal


def permit(permission: str) -> Callable[..., Principal]:
    """Dependencia que exige un permiso atómico en FastAPI (403 si falta)."""

    def _check(principal: Principal = Depends(authenticate)) -> Principal:
        if permission not in principal.permissions:
            raise HTTPException(403, "Tu rol no tiene permiso para esta operación.")
        return principal

    return _check


def permit_page(page: str) -> Callable[..., Principal]:
    """Atajo para proteger un endpoint con el permiso de su página Angular."""
    return permit(PAGE_PERMISSIONS[page])


def require_session(principal: Principal = Depends(authenticate)) -> Principal:
    return principal


router = APIRouter(prefix="/api/auth", tags=["autenticación"])


def _log(db: Session, principal: Principal, action: str, detail: str = "") -> None:
    db.add(
        UserActivity(
            parking_lot_id=principal.parking_lot_id,
            user_id=principal.user_id,
            employee_id=principal.employee_id,
            action=action,
            detail=detail[:240],
            actor=principal.display_name,
        )
    )


def _validate_new_password(value: str, current: str) -> str:
    password = (value or "").strip()
    if len(password) < 12:
        raise HTTPException(422, "La contraseña debe tener al menos 12 caracteres.")
    if len(password) > 200:
        raise HTTPException(422, "La contraseña no puede superar los 200 caracteres.")
    if password == current:
        raise HTTPException(422, "La nueva contraseña debe ser diferente de la actual.")
    return password


@router.post("/login")
def login(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Verifica credenciales y devuelve un token persistente de sesión."""
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    lot_raw = payload.get("parking_lot_id")
    if not username or not password:
        raise HTTPException(422, "Ingresa usuario y contraseña.")
    query = select(UserAccount).where(UserAccount.username == username)
    if lot_raw:
        query = query.where(UserAccount.parking_lot_id == int(lot_raw))
    user = db.scalars(query.order_by(UserAccount.id)).first()
    if not user or not verify_password(password, user.password_hash):
        # No revelamos si el usuario existe.
        raise HTTPException(401, "El usuario o la contraseña no coinciden.")
    if not user.active:
        raise HTTPException(403, "Tu cuenta está desactivada. Contacta al administrador.")
    user.last_login = datetime.now()
    principal = build_principal(db, user)
    _log(db, principal, "LOGIN", "Inicio de sesión")
    db.commit()
    return {
        "access_token": create_token(principal),
        "token_type": "bearer",
        "expires_in_hours": TOKEN_TTL_HOURS,
        "user": principal.as_dict(),
    }


@router.get("/me")
def me(principal: Principal = Depends(require_session)) -> dict[str, Any]:
    """Datos vigentes de la sesión (rol, permisos, parqueadero)."""
    return principal.as_dict()


@router.post("/change-password")
def change_password(
    payload: dict[str, Any],
    principal: Principal = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Permite sustituir la contraseña temporal y libera el bloqueo de sesión."""
    user = db.get(UserAccount, principal.user_id)
    if not user or not verify_password(payload.get("current_password") or "", user.password_hash):
        raise HTTPException(403, "La contraseña actual no es correcta.")
    new_password = _validate_new_password(payload.get("new_password") or "", payload.get("current_password") or "")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.updated_at = datetime.now()
    _log(db, principal, "PASSWORD_CHANGED", user.username)
    db.commit()
    updated = build_principal(db, user)
    return {"status": "OK", "message": "Contraseña actualizada.", "user": updated.as_dict()}


@router.post("/logout")
def logout(
    principal: Principal = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Registra el cierre de sesión; el cliente descarta el token."""
    _log(db, principal, "LOGOUT", "Cierre de sesión")
    db.commit()
    return {"status": "OK", "message": "Sesión cerrada."}
