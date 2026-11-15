"""Runtime secret reader for the existing SSM or Secrets Manager permissions."""
from __future__ import annotations

import json

import boto3


def read_secret(identifier: str, *, store: str = "ssm", client=None) -> str:
    if not identifier:
        raise ValueError("A secret identifier is required")
    if store == "ssm":
        client = client or boto3.client("ssm")
        parameter = client.get_parameter(Name=identifier, WithDecryption=True)["Parameter"]
        if parameter.get("Type") != "SecureString":
            raise ValueError("The producer/GCP secret must be an encrypted SecureString")
        return parameter["Value"]
    if store == "secretsmanager":
        client = client or boto3.client("secretsmanager")
        secret = client.get_secret_value(SecretId=identifier)
        if not isinstance(secret.get("SecretString"), str):
            raise ValueError("Expected a text secret")
        return secret["SecretString"]
    raise ValueError("Unsupported secret store")


def read_json_secret(identifier: str, *, store: str = "ssm", client=None) -> dict:
    value = json.loads(read_secret(identifier, store=store, client=client))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object secret")
    return value
