import base64
import datetime
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from src.auth.firebase_tokens import FirebaseCertProvider, TokenError, verify_id_token

PROJECT = "ccs-arquifusion"
KID = "kid-1"


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeProvider:
    def __init__(self, keys):
        self.keys = keys

    def get_key(self, kid):
        if kid not in self.keys:
            raise TokenError("UNKNOWN_KEY")
        return self.keys[kid]


def make_token(private_key, kid=KID, **overrides):
    now = int(time.time())
    claims = {
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "sub": "uid-123",
        "iat": now - 10,
        "exp": now + 3600,
        "auth_time": now - 10,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def code_of(token, provider):
    with pytest.raises(TokenError) as exc:
        verify_id_token(token, PROJECT, provider)
    return exc.value.code


def test_valid_token_returns_claims(key):
    claims = verify_id_token(
        make_token(key), PROJECT, FakeProvider({KID: key.public_key()})
    )
    assert claims["sub"] == "uid-123"


def test_token_from_other_project_is_rejected(key):
    p = FakeProvider({KID: key.public_key()})
    assert code_of(make_token(key, aud="otro-proyecto"), p) == "BAD_AUDIENCE"
    assert (
        code_of(make_token(key, iss="https://securetoken.google.com/otro-proyecto"), p)
        == "BAD_ISSUER"
    )


def test_expired_token_is_rejected(key):
    p = FakeProvider({KID: key.public_key()})
    assert code_of(make_token(key, exp=int(time.time()) - 5), p) == "EXPIRED"


def test_forged_signature_is_rejected(key, other_key):
    p = FakeProvider({KID: key.public_key()})
    assert code_of(make_token(other_key), p) == "BAD_SIGNATURE"


def test_unknown_kid_is_rejected(key):
    p = FakeProvider({KID: key.public_key()})
    assert code_of(make_token(key, kid="otro-kid"), p) == "UNKNOWN_KEY"


def test_future_iat_and_auth_time_are_rejected(key):
    p = FakeProvider({KID: key.public_key()})
    future = int(time.time()) + 600
    assert code_of(make_token(key, iat=future), p) == "NOT_YET_VALID"
    assert code_of(make_token(key, auth_time=future), p) == "BAD_AUTH_TIME"


def test_missing_or_bad_subject_is_rejected(key):
    p = FakeProvider({KID: key.public_key()})
    assert code_of(make_token(key, sub=None), p) == "INVALID"
    assert code_of(make_token(key, sub=""), p) == "BAD_SUBJECT"
    assert code_of(make_token(key, sub="x" * 129), p) == "BAD_SUBJECT"


def test_missing_auth_time_is_rejected(key):
    assert (
        code_of(make_token(key, auth_time=None), FakeProvider({KID: key.public_key()}))
        == "BAD_AUTH_TIME"
    )


def test_garbage_and_empty_tokens_are_rejected(key):
    p = FakeProvider({KID: key.public_key()})
    assert code_of("esto-no-es-un-jwt", p) == "MALFORMED"
    assert code_of("", p) == "MISSING_TOKEN"
    assert code_of(None, p) == "MISSING_TOKEN"


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_alg_none_is_rejected(key):
    now = int(time.time())
    payload = {
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "sub": "u",
        "iat": now,
        "exp": now + 60,
        "auth_time": now,
    }
    token = f"{_b64({'alg': 'none', 'kid': KID})}.{_b64(payload)}."
    assert code_of(token, FakeProvider({KID: key.public_key()})) == "BAD_ALGORITHM"


def test_hs256_signed_with_public_key_is_rejected(key):
    """Ataque clásico: firmar con HMAC usando la clave pública como secreto."""
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    now = int(time.time())
    payload = {
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "sub": "u",
        "iat": now,
        "exp": now + 60,
        "auth_time": now,
    }
    signing_input = f"{_b64({'alg': 'HS256', 'kid': KID})}.{_b64(payload)}"
    sig = (
        base64.urlsafe_b64encode(
            hmac.new(pem, signing_input.encode(), hashlib.sha256).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    assert (
        code_of(f"{signing_input}.{sig}", FakeProvider({KID: key.public_key()}))
        == "BAD_ALGORITHM"
    )


# ---------- caché de certificados ----------


def self_signed_pem(private_key) -> str:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(1)
        .not_valid_before(datetime.datetime(2020, 1, 1))
        .not_valid_after(datetime.datetime(2099, 1, 1))
        .sign(private_key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


class FakeFetch:
    def __init__(self, certs, cache_control="public, max-age=100, must-revalidate"):
        self.certs, self.cache_control, self.calls = certs, cache_control, 0

    def __call__(self):
        self.calls += 1
        return json.dumps(self.certs), self.cache_control


def test_cert_provider_parses_certificates_and_verifies_tokens(key):
    fetch = FakeFetch({KID: self_signed_pem(key)})
    provider = FirebaseCertProvider(fetch=fetch, clock=lambda: 1000.0)
    claims = verify_id_token(make_token(key), PROJECT, provider)
    assert claims["sub"] == "uid-123"


def test_cert_provider_caches_until_max_age(key):
    now = [1000.0]
    fetch = FakeFetch({KID: self_signed_pem(key)})
    provider = FirebaseCertProvider(fetch=fetch, clock=lambda: now[0])
    provider.get_key(KID)
    provider.get_key(KID)
    assert fetch.calls == 1
    now[0] += 101  # venció max-age=100
    provider.get_key(KID)
    assert fetch.calls == 2


def test_unknown_kid_refetch_is_rate_limited(key):
    now = [1000.0]
    fetch = FakeFetch({KID: self_signed_pem(key)})
    provider = FirebaseCertProvider(
        fetch=fetch, clock=lambda: now[0], min_refresh_seconds=60
    )
    provider.get_key(KID)
    for _ in range(5):  # un atacante insiste con kid inventados
        with pytest.raises(TokenError):
            provider.get_key("inventado")
    assert fetch.calls == 1
    now[0] += 61  # pasado el mínimo, sí se permite volver a mirar (rotación de claves)
    with pytest.raises(TokenError):
        provider.get_key("inventado")
    assert fetch.calls == 2


def test_cert_provider_keeps_old_keys_if_google_is_unreachable(key):
    now = [1000.0]
    fetch = FakeFetch({KID: self_signed_pem(key)})
    provider = FirebaseCertProvider(fetch=fetch, clock=lambda: now[0])
    provider.get_key(KID)

    def broken():
        raise OSError("sin red")

    provider._fetch = broken
    now[0] += 500
    assert provider.get_key(KID) is not None


def test_cert_provider_fails_closed_without_any_keys():
    def broken():
        raise OSError("sin red")

    provider = FirebaseCertProvider(fetch=broken, clock=lambda: 1000.0)
    with pytest.raises(TokenError) as exc:
        provider.get_key(KID)
    assert exc.value.code == "KEYS_UNAVAILABLE"
