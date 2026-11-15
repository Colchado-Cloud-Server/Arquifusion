"""Shared configuration for CloudShell commands. Never read or print secret values."""
from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import urlparse

import boto3
from dotenv import load_dotenv
import yaml

ROOT = Path(__file__).resolve().parents[1]
TABLE_ENV = {
    "operations": "OPERATIONS_TABLE", "machineModels": "MACHINE_MODELS_TABLE",
    "machines": "MACHINES_TABLE", "eventDedup": "EVENT_DEDUP_TABLE", "incidents": "INCIDENTS_TABLE",
    "activeIncidents": "ACTIVE_INCIDENTS_TABLE", "maintenanceEvents": "MAINTENANCE_EVENTS_TABLE",
    "technicians": "TECHNICIANS_TABLE", "parts": "PARTS_TABLE", "partReservations": "PART_RESERVATIONS_TABLE",
    "users": "USERS_TABLE", "notifications": "NOTIFICATIONS_TABLE", "analytics": "ANALYTICS_TABLE",
}
ROLE_PRINCIPALS = {
    "LAMBDA_ROLE_ARN": "lambda.amazonaws.com", "SFN_ROLE_ARN": "states.amazonaws.com",
    "EVENTS_START_SFN_ROLE_ARN": "events.amazonaws.com", "SCHEDULER_ROLE_ARN": "scheduler.amazonaws.com",
    "SIMULATOR_ROLE_ARN": "lambda.amazonaws.com", "INGEST_ROLE_ARN": "lambda.amazonaws.com",
}
ROLE_RE = re.compile(r"^arn:aws:iam::([0-9]{12}):role/[A-Za-z0-9+=,.@_/-]+$")


def environment() -> dict[str, str]:
    load_dotenv(ROOT / ".env", override=False)
    return dict(os.environ)


def session(env: dict[str, str], *, profile: str | None = None, region: str | None = None):
    return boto3.Session(profile_name=profile or env.get("AWS_PROFILE") or None,
                         region_name=region or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-east-1")


def verified_session(env: dict[str, str]):
    aws = session(env)
    expected = env.get("EXPECTED_AWS_ACCOUNT_ID")
    if not expected or aws.client("sts").get_caller_identity()["Account"] != expected:
        raise ValueError("Active account does not match EXPECTED_AWS_ACCOUNT_ID")
    return aws


def configuration_errors(env: dict[str, str]) -> list[str]:
    errors = []
    account = env.get("EXPECTED_AWS_ACCOUNT_ID", "")
    if not re.fullmatch(r"[0-9]{12}", account):
        errors.append("EXPECTED_AWS_ACCOUNT_ID must identify the verified lab account")
    stage = env.get("STAGE", "dev")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,15}", stage):
        errors.append("STAGE must be a short resource-safe identifier")
    for variable, principal in ROLE_PRINCIPALS.items():
        optional = variable in {"SIMULATOR_ROLE_ARN", "INGEST_ROLE_ARN"} or (
            variable == "SCHEDULER_ROLE_ARN" and env.get("ENABLE_SCHEDULER", "false") == "false")
        value = env.get(variable, "")
        if optional and not value:
            if variable in {"SIMULATOR_ROLE_ARN", "INGEST_ROLE_ARN"} and variable in env:
                errors.append(f"Omit {variable} instead of defining an empty override")
            continue
        match = ROLE_RE.fullmatch(value)
        if not match or match.group(1) != account:
            errors.append(f"{variable} must be an existing role ARN in the verified account for {principal}")
    for flag in ("ENABLE_SCHEDULER", "ENABLE_ALARMS", "ENABLE_TELEMETRY_CONSUMER", "USE_EXISTING_TABLES", "DEMO_SEED_ENABLED"):
        if env.get(flag, "false") not in {"true", "false"}:
            errors.append(f"{flag} must be true or false")
    for variable in TABLE_ENV.values():
        if variable in env and not re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", env[variable]):
            errors.append(f"{variable} must be a valid nonempty table name or be omitted")
        flag = "USE_EXISTING_" + variable
        if env.get(flag, "false") not in {"true", "false"}:
            errors.append(f"{flag} must be true or false")
        if env.get(flag) == "true" and not env.get(variable):
            errors.append(f"{variable} is required when {flag}=true")
    origin = env.get("PAGES_ORIGIN", "")
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]+)?", origin):
        errors.append("PAGES_ORIGIN must be an exact HTTPS origin without a path or wildcard")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", env.get("DEPLOYMENT_BUCKET", "")):
        errors.append("DEPLOYMENT_BUCKET must name the authorized existing private artifacts bucket")
    if not env.get("FIREBASE_PROJECT_ID"):
        errors.append("FIREBASE_PROJECT_ID is required")
    if env.get("SECRET_STORE", "ssm") not in {"ssm", "secretsmanager"}:
        errors.append("SECRET_STORE must be ssm or secretsmanager")
    queue_variables = ("EXISTING_TELEMETRY_QUEUE_ARN", "EXISTING_TELEMETRY_QUEUE_URL",
                       "EXISTING_TELEMETRY_DLQ_ARN", "EXISTING_TELEMETRY_DLQ_URL")
    if any(env.get(name) for name in queue_variables) and not all(env.get(name) for name in queue_variables):
        errors.append("Existing SQS configuration requires both ARNs and both URLs")
    for name in (queue_variables[0], queue_variables[2]):
        arn = env.get(name)
        if arn and not re.fullmatch(rf"arn:aws:sqs:[a-z0-9-]+:{account}:[A-Za-z0-9_-]+", arn):
            errors.append(f"{name} must be a Standard SQS ARN in the verified account")
    for arn_name, url_name in ((queue_variables[0], queue_variables[1]), (queue_variables[2], queue_variables[3])):
        if env.get(arn_name) and env.get(url_name):
            parts = env[arn_name].split(":")
            parsed = urlparse(env[url_name])
            if len(parts) != 6 or parsed.scheme != "https" or parsed.hostname != f"sqs.{parts[3]}.amazonaws.com" or parsed.path != f"/{account}/{parts[5]}":
                errors.append(f"{url_name} must match its queue ARN")
            elif parts[3] != env.get("AWS_REGION", "us-east-1"):
                errors.append(f"{arn_name} must use the deployment region")
    if env.get(queue_variables[0]) and env.get(queue_variables[0]) == env.get(queue_variables[2]):
        errors.append("Source queue and DLQ must be distinct")
    if env.get("USE_EXISTING_TABLES") == "true" and any(not env.get(name) for name in TABLE_ENV.values()):
        errors.append("Existing tables mode requires all thirteen explicit table names")
    configured_tables = [env[name] for name in TABLE_ENV.values() if env.get(name)]
    if len(configured_tables) != len(set(configured_tables)):
        errors.append("Table names must be distinct")
    return errors


def function_definitions() -> dict:
    return yaml.safe_load((ROOT / "infra/functions.yml").read_text(encoding="utf-8"))
