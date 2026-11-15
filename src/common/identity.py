"""Identidad del solicitante dentro de cada Lambda (AUTH-02).

El authorizer ya verificó el token. Cada handler vuelve a comprobar que la
operación pedida está dentro del alcance del usuario (defensa en profundidad).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


class Forbidden(Exception):
    """El usuario no tiene permiso sobre la operación o la acción pedida (HTTP 403)."""


@dataclass(frozen=True)
class Identity:
    uid: str
    email: str = ""
    roles: dict = field(default_factory=dict)  # {operation_id: ROL}
    technician_id: str | None = None


def from_event(event: dict) -> Identity:
    ctx = (event.get("requestContext") or {}).get("authorizer", {}).get("lambda") or {}
    if not ctx.get("uid"):
        raise Forbidden("Sin identidad verificada")
    return Identity(
        uid=ctx["uid"],
        email=ctx.get("email", ""),
        roles=json.loads(ctx.get("roles") or "{}"),
        technician_id=ctx.get("technician_id") or None,
    )


def require_access(identity: Identity, operation_id: str, allowed_roles=None) -> str:
    """Devuelve el rol del usuario en la operación o lanza Forbidden."""
    role = identity.roles.get(operation_id)
    if role is None:
        raise Forbidden("Operación fuera de alcance")
    if allowed_roles is not None and role not in allowed_roles:
        raise Forbidden("Rol sin permiso para esta acción")
    return role
