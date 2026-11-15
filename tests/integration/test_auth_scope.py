"""Authorizer + perfiles reales del catálogo demo + alcance por operación (AUTH-04)."""

import json
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.admin.seed_service import load_catalog
from src.auth.firebase_authorizer import make_handler
from src.common.identity import Forbidden, from_event, require_access

PROJECT = "ccs-arquifusion"
KID = "kid-1"
CATALOG = load_catalog(
    Path(__file__).resolve().parents[2] / "seed" / "demo_catalog.json"
)
USERS = {u["firebase_uid"]: u for u in CATALOG["users"]}
UID = {u["email"].split("@")[0]: u["firebase_uid"] for u in CATALOG["users"]}


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Provider:
    def __init__(self, key):
        self.key = key

    def get_key(self, kid):
        from src.auth.firebase_tokens import TokenError

        if kid != KID:
            raise TokenError("UNKNOWN_KEY")
        return self.key.public_key()


def token_for(key, sub, project=PROJECT, **extra):
    now = int(time.time())
    claims = {
        "iss": f"https://securetoken.google.com/{project}",
        "aud": project,
        "sub": sub,
        "iat": now - 5,
        "exp": now + 3600,
        "auth_time": now - 5,
        **extra,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})


def call(key, headers, users=None):
    users = USERS if users is None else users
    handler = make_handler(PROJECT, Provider(key), lambda uid: users.get(uid))
    return handler({"headers": headers})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def identity_from(result):
    return from_event({"requestContext": {"authorizer": {"lambda": result["context"]}}})


def test_valid_user_with_profile_is_authorized(key):
    result = call(key, bearer(token_for(key, UID["supervisor"])))
    assert result["isAuthorized"] is True
    ident = identity_from(result)
    assert ident.uid == UID["supervisor"]
    assert ident.roles == {"op-demo": "SUPERVISOR"}


def test_technician_context_carries_technician_id(key):
    ident = identity_from(call(key, bearer(token_for(key, UID["tecnico"]))))
    assert ident.technician_id == "tech-001"


def test_missing_or_malformed_header_is_denied(key):
    assert call(key, {})["isAuthorized"] is False
    assert call(key, {"Authorization": "Basic abc"})["isAuthorized"] is False
    assert call(key, {"Authorization": "Bearer"})["isAuthorized"] is False
    assert call(key, bearer("no-es-un-token"))["isAuthorized"] is False


def test_header_name_is_case_insensitive(key):
    result = call(key, {"authorization": f"Bearer {token_for(key, UID['admin'])}"})
    assert result["isAuthorized"] is True


def test_token_from_another_project_is_denied(key):
    assert (
        call(key, bearer(token_for(key, UID["admin"], project="otro-proyecto")))[
            "isAuthorized"
        ]
        is False
    )


def test_expired_token_is_denied(key):
    assert (
        call(key, bearer(token_for(key, UID["admin"], exp=int(time.time()) - 5)))[
            "isAuthorized"
        ]
        is False
    )


def test_valid_token_without_profile_is_denied(key):
    assert call(key, bearer(token_for(key, "uid-desconocido")))["isAuthorized"] is False


def test_disabled_user_is_denied(key):
    users = json.loads(json.dumps(USERS))
    users[UID["operador"]]["enabled"] = False
    assert (
        call(key, bearer(token_for(key, UID["operador"])), users)["isAuthorized"]
        is False
    )


def test_uid_comes_from_token_not_from_client_fields(key):
    """Un campo extra (X-User-Id) o un claim 'uid' falso no cambian la identidad."""
    headers = {
        **bearer(token_for(key, UID["operador"], uid=UID["admin"])),
        "X-User-Id": UID["admin"],
    }
    ident = identity_from(call(key, headers))
    assert ident.uid == UID["operador"]
    assert ident.roles == {"op-demo": "OPERADOR"}


def test_other_operation_is_forbidden(key):
    ident = identity_from(call(key, bearer(token_for(key, UID["supervisor"]))))
    assert require_access(ident, "op-demo") == "SUPERVISOR"
    with pytest.raises(Forbidden):
        require_access(ident, "op-otra")


def test_role_restriction_is_enforced(key):
    operador = identity_from(call(key, bearer(token_for(key, UID["operador"]))))
    with pytest.raises(Forbidden):
        require_access(operador, "op-demo", allowed_roles={"SUPERVISOR", "ADMIN"})
    supervisor = identity_from(call(key, bearer(token_for(key, UID["supervisor"]))))
    assert (
        require_access(supervisor, "op-demo", allowed_roles={"SUPERVISOR", "ADMIN"})
        == "SUPERVISOR"
    )


def test_event_without_authorizer_context_is_forbidden():
    with pytest.raises(Forbidden):
        from_event({"requestContext": {}})
