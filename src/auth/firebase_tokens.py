"""Validación de ID tokens de Firebase (AUTH-01).

Un ID token es un JWT firmado por Google (RS256). Para aceptarlo se comprueba:
firma (con la clave pública que corresponde a su `kid`), `aud` = nuestro
proyecto, `iss` = securetoken de nuestro proyecto, `exp`, `iat`, `auth_time`
y `sub` (el UID del usuario). El UID siempre sale del token verificado, nunca
de un campo que mande el cliente.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request

import jwt
from cryptography import x509

CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)
DEFAULT_MAX_AGE = 3600
MIN_REFRESH_SECONDS = 60  # tope de consultas a Google cuando llega un kid desconocido


class TokenError(Exception):
    """Token rechazado. `code` es estable y apto para logs (nunca incluye el token)."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _http_fetch() -> tuple[str, str]:
    req = urllib.request.Request(CERTS_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310 (URL fija https)
        return resp.read().decode("utf-8"), resp.headers.get("Cache-Control", "")


class FirebaseCertProvider:
    """Entrega la clave pública de un `kid`, con caché según Cache-Control.

    Google rota sus claves; si llega un `kid` que no conocemos se vuelve a
    consultar, pero como máximo una vez por minuto (para que un atacante no
    pueda forzar consultas ilimitadas con tokens inventados).
    """

    def __init__(
        self, fetch=None, clock=time.time, min_refresh_seconds=MIN_REFRESH_SECONDS
    ):
        self._fetch = fetch or _http_fetch
        self._clock = clock
        self._min_refresh = min_refresh_seconds
        self._keys: dict = {}
        self._expires_at = 0.0
        self._last_fetch: float | None = None

    def _refresh(self, now: float) -> None:
        self._last_fetch = now
        try:
            body, cache_control = self._fetch()
            certs = json.loads(body)
            keys = {
                kid: x509.load_pem_x509_certificate(pem.encode("utf-8")).public_key()
                for kid, pem in certs.items()
            }
        except Exception as exc:  # red caída, JSON o certificado inválido
            if not self._keys:
                raise TokenError(
                    "KEYS_UNAVAILABLE", "No se pudieron obtener las claves públicas"
                ) from exc
            return  # se siguen usando las claves anteriores
        match = re.search(r"max-age=(\d+)", cache_control or "")
        max_age = int(match.group(1)) if match else DEFAULT_MAX_AGE
        self._keys = keys
        self._expires_at = now + max_age

    def get_key(self, kid: str):
        now = self._clock()
        if now >= self._expires_at:
            self._refresh(now)
        key = self._keys.get(kid)
        if key is None and (
            self._last_fetch is None or now - self._last_fetch >= self._min_refresh
        ):
            self._refresh(now)
            key = self._keys.get(kid)
        if key is None:
            raise TokenError("UNKNOWN_KEY", "kid desconocido")
        return key


def verify_id_token(token: str, project_id: str, key_provider, leeway: int = 0) -> dict:
    """Devuelve los claims si el token es válido; si no, lanza TokenError."""
    if not isinstance(token, str) or not token.strip():
        raise TokenError("MISSING_TOKEN")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise TokenError("MALFORMED") from exc
    if header.get("alg") != "RS256":
        raise TokenError("BAD_ALGORITHM")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise TokenError("NO_KID")

    key = key_provider.get_key(kid)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=f"https://securetoken.google.com/{project_id}",
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
            leeway=leeway,
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("EXPIRED") from exc
    except jwt.InvalidAudienceError as exc:
        raise TokenError("BAD_AUDIENCE") from exc
    except jwt.InvalidIssuerError as exc:
        raise TokenError("BAD_ISSUER") from exc
    except jwt.ImmatureSignatureError as exc:
        raise TokenError("NOT_YET_VALID") from exc
    except jwt.InvalidSignatureError as exc:
        raise TokenError("BAD_SIGNATURE") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("INVALID") from exc

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub or len(sub) > 128:
        raise TokenError("BAD_SUBJECT")
    auth_time = claims.get("auth_time")
    if not isinstance(auth_time, (int, float)) or auth_time > time.time() + leeway:
        raise TokenError("BAD_AUTH_TIME")
    return claims
