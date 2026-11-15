"""AWS-01/02: identity, CloudFormation, artifacts and role trust checks from CloudShell."""
from __future__ import annotations

import argparse
import json
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError

from scripts.aws_config import ROLE_PRINCIPALS, ROLE_RE, environment, session


def run_checks(env: dict, aws, *, write_test: bool = False, simulate_passrole: bool = False) -> dict:
    checks = []

    def probe(name, call):
        try:
            result = call()
            checks.append({"check": name, "status": "PASS"})
            return result
        except (BotoCoreError, ClientError) as exc:
            code = exc.response["Error"]["Code"] if isinstance(exc, ClientError) else type(exc).__name__
            checks.append({"check": name, "status": "NOT_VERIFIED", "aws_error": code})
            return None

    identity = probe("sts:GetCallerIdentity", lambda: aws.client("sts").get_caller_identity())
    if identity is None:
        return {"status": "BLOCKED", "checks": checks}
    account = identity["Account"]
    expected = env.get("EXPECTED_AWS_ACCOUNT_ID")
    arn = identity["Arn"]
    actor_role = arn.split(":assumed-role/", 1)[1].split("/")[0] if ":assumed-role/" in arn else None
    info = {"account": account, "region": aws.region_name, "actor_role": actor_role}
    if not expected or account != expected:
        checks.append({"check": "expected_account", "status": "BLOCKED"})
        return {"status": "BLOCKED", **info, "checks": checks}
    probe("cloudformation:ListStacks", lambda: aws.client("cloudformation").list_stacks())
    bucket = env.get("DEPLOYMENT_BUCKET")
    if bucket:
        s3 = aws.client("s3")
        accessible = probe("artifacts:HeadBucket", lambda: s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account))
        if accessible is not None:
            location = probe("artifacts:GetBucketLocation", lambda: s3.get_bucket_location(Bucket=bucket, ExpectedBucketOwner=account))
            if location is not None and (location.get("LocationConstraint") or "us-east-1") != aws.region_name:
                checks.append({"check": "artifacts:Region", "status": "BLOCKED"})
            public = probe("artifacts:GetPublicAccessBlock", lambda: s3.get_public_access_block(Bucket=bucket, ExpectedBucketOwner=account))
            if public is not None and not all(public.get("PublicAccessBlockConfiguration", {}).get(key) is True for key in (
                "BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets",
            )):
                checks.append({"check": "artifacts:Private", "status": "BLOCKED"})
            if write_test:
                key = f"serverless/arquifusion/{env.get('STAGE', 'dev')}/aws-01/{uuid4().hex}.txt"
                payload = b"ArquiFusion AWS-01 synthetic permissions check\n"
                created = probe("artifacts:PutObject", lambda: s3.put_object(Bucket=bucket, Key=key, Body=payload, ServerSideEncryption="AES256", ExpectedBucketOwner=account))
                if created is not None:
                    try:
                        response = probe("artifacts:GetObject", lambda: s3.get_object(Bucket=bucket, Key=key, ExpectedBucketOwner=account))
                        if response is not None:
                            try:
                                if response["Body"].read() != payload:
                                    checks.append({"check": "artifacts:Roundtrip", "status": "BLOCKED"})
                            finally:
                                response["Body"].close()
                    finally:
                        args = {"Bucket": bucket, "Key": key, "ExpectedBucketOwner": account}
                        if created.get("VersionId"):
                            args["VersionId"] = created["VersionId"]
                        probe("artifacts:DeleteProbe", lambda: s3.delete_object(**args))
    else:
        checks.append({"check": "artifacts", "status": "NOT_CONFIGURED"})
    iam = aws.client("iam")
    for variable, principal in ROLE_PRINCIPALS.items():
        role_arn = env.get(variable)
        optional = variable in {"INGEST_ROLE_ARN", "SIMULATOR_ROLE_ARN"} or (
            variable == "SCHEDULER_ROLE_ARN" and env.get("ENABLE_SCHEDULER", "false") != "true")
        if not role_arn:
            if not optional:
                checks.append({"check": variable, "status": "NOT_CONFIGURED"})
            continue
        match = ROLE_RE.fullmatch(role_arn)
        if not match or match.group(1) != account:
            checks.append({"check": variable, "status": "BLOCKED"})
            continue
        role = probe(variable + ":GetRole", lambda: iam.get_role(RoleName=role_arn.rsplit("/", 1)[1]))
        if role is None:
            continue
        if role["Role"]["Arn"] != role_arn:
            checks.append({"check": variable + ":Arn", "status": "BLOCKED"})
            continue
        policy = role["Role"]["AssumeRolePolicyDocument"]
        statements = policy.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        suitable = False
        for statement in statements:
            services = statement.get("Principal", {})
            services = services.get("Service", []) if isinstance(services, dict) else []
            services = [services] if isinstance(services, str) else services
            actions = statement.get("Action", [])
            actions = [actions] if isinstance(actions, str) else actions
            if statement.get("Effect") == "Allow" and principal in services and any(action in actions for action in ("sts:AssumeRole", "sts:*", "*")):
                suitable = True
        if not suitable or any(statement.get("Condition") or statement.get("Effect") == "Deny" for statement in statements):
            checks.append({"check": variable + ":Trust", "status": "REQUIRES_REVIEW"})
        else:
            checks.append({"check": variable + ":Trust", "status": "PASS"})
        if simulate_passrole and actor_role:
            actor = probe("actor:GetRole", lambda: iam.get_role(RoleName=actor_role))
            if actor is not None:
                simulation = probe(variable + ":SimulatePassRole", lambda: iam.simulate_principal_policy(
                    PolicySourceArn=actor["Role"]["Arn"], ActionNames=["iam:PassRole"], ResourceArns=[role_arn],
                    ContextEntries=[{"ContextKeyName": "iam:PassedToService", "ContextKeyValues": [principal], "ContextKeyType": "string"}],
                ))
                if simulation is not None:
                    rows = simulation.get("EvaluationResults", [])
                    allowed = bool(rows) and all(row.get("EvalDecision") == "allowed" for row in rows)
                    checks.append({"check": variable + ":PassRoleSimulation", "status": "SIMULATED_ALLOW" if allowed else "REQUIRES_REVIEW"})
    incomplete = any(check["status"] not in {"PASS", "SIMULATED_ALLOW"} for check in checks)
    return {"status": "PARTIAL" if incomplete else "READ_CHECKS_PASSED", **info, "checks": checks,
            "effective_deployment_permissions": "NOT_VERIFIED", "write_test_requested": write_test}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile")
    parser.add_argument("--region")
    parser.add_argument("--write-test", action="store_true", help="Put/get/delete one unique synthetic object in the artifacts bucket")
    parser.add_argument("--simulate-passrole", action="store_true", help="Optional IAM simulation; does not prove session/SCP/resource-policy permissions")
    args = parser.parse_args()
    env = environment()
    try:
        report = run_checks(env, session(env, profile=args.profile, region=args.region), write_test=args.write_test,
                            simulate_passrole=args.simulate_passrole)
    except (BotoCoreError, ClientError) as exc:
        report = {"status": "BLOCKED", "error_type": type(exc).__name__}
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "READ_CHECKS_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
