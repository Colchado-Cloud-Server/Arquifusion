"""Lambda authorizer (REQUEST, payload 2.0, respuesta simple) para /api/*.

Flujo: token Bearer -> verificación de firma y claims -> perfil habilitado en
t-users -> contexto con uid y roles por operación para los handlers.

Sin token o con uno inválido responde isAuthorized=false (API Gateway devuelve 403).
Si el header Authorization falta por completo, API Gateway responde 401 por sí mismo
cuando se configura identitySource = $request.header.Authorization.
"""

from __future__ import annotations

import json
import logging
import os

from src.auth.firebase_tokens import FirebaseCertProvider, TokenError, verify_id_token

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DENY = {"isAuthorized": False}


def extract_bearer(event: dict) -> str | None:
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    value = headers.get("authorization")
    if not value:
        return None
    parts = value.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def make_handler(project_id: str, key_provider, profile_loader):
    def handler(event, context=None):
        token = extract_bearer(event)
        if not token:
            logger.info(json.dumps({"auth": "deny", "reason": "MISSING_TOKEN"}))
            return dict(DENY)
        try:
            claims = verify_id_token(token, project_id, key_provider)
        except TokenError as exc:
            logger.info(
                json.dumps({"auth": "deny", "reason": exc.code})
            )  # nunca se registra el token
            return dict(DENY)

        uid = claims["sub"]
        profile = profile_loader(uid)
        if not profile:
            logger.info(
                json.dumps({"auth": "deny", "reason": "NO_PROFILE", "uid": uid})
            )
            return dict(DENY)
        if profile.get("enabled") is not True:
            logger.info(json.dumps({"auth": "deny", "reason": "DISABLED", "uid": uid}))
            return dict(DENY)

        return {
            "isAuthorized": True,
            # En el contexto de HTTP API solo viajan valores simples: roles va como JSON en texto.
            "context": {
                "uid": uid,
                "email": str(profile.get("email", "")),
                "roles": json.dumps(profile.get("roles", {})),
                "technician_id": str(profile.get("technician_id", "")),
            },
        }

    return handler


_handler = None


def handler(event, context=None):
    """Punto de entrada en Lambda: configura dependencias la primera vez."""
    global _handler
    if _handler is None:
        from src.auth.profiles import DynamoProfileLoader

        _handler = make_handler(
            os.environ["FIREBASE_PROJECT_ID"],
            FirebaseCertProvider(),
            DynamoProfileLoader(os.environ["USERS_TABLE"]),
        )
    return _handler(event, context)
