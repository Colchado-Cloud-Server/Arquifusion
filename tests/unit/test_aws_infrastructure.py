from copy import deepcopy
import json
from pathlib import Path
import os
import subprocess
import sys
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
import yaml

from scripts.aws_config import ROOT, TABLE_ENV, configuration_errors
from scripts.package_backend import build, source_files
from scripts.validate_infra import missing_handlers, static_errors, workflow_errors


@pytest.fixture
def valid_env():
    return {"STAGE": "dev", "AWS_REGION": "us-east-1", "EXPECTED_AWS_ACCOUNT_ID": "111111111111",
            "PAGES_ORIGIN": "https://arquifusion-test.pages.dev", "FIREBASE_PROJECT_ID": "arquifusion-test",
            "DEPLOYMENT_BUCKET": "af-dev-111111111111-us-east-1-artifacts",
            **{key: "arn:aws:iam::111111111111:role/AuthorizedLabRole" for key in (
                "LAMBDA_ROLE_ARN", "SFN_ROLE_ARN", "EVENTS_START_SFN_ROLE_ARN")}}


def test_complete_static_resource_graph_has_no_role_creation():
    assert static_errors() == []
    tables = yaml.safe_load((ROOT / "infra/tables.yml").read_text())["Resources"]
    assert len(tables) == 13
    assert all(table["Properties"]["BillingMode"] == "PAY_PER_REQUEST" for table in tables.values())
    assert tables["EventDedupTable"]["Properties"]["TimeToLiveSpecification"] == {"AttributeName": "expires_at", "Enabled": True}
    assert len(tables["IncidentsTable"]["Properties"]["GlobalSecondaryIndexes"]) == 3


def test_valid_environment_and_optional_scheduler_role(valid_env):
    assert configuration_errors(valid_env) == []
    valid_env["ENABLE_SCHEDULER"] = "true"
    assert any("SCHEDULER_ROLE_ARN" in error for error in configuration_errors(valid_env))


@pytest.mark.parametrize("field,value", [
    ("EXPECTED_AWS_ACCOUNT_ID", ""), ("LAMBDA_ROLE_ARN", "arn:aws:iam::222222222222:role/OtherAccount"),
    ("PAGES_ORIGIN", "*"), ("PAGES_ORIGIN", "https://test.pages.dev/path"),
    ("PAGES_ORIGIN", "http://test.pages.dev"), ("ENABLE_SCHEDULER", "yes"),
    ("USE_EXISTING_TABLES", "true"), ("SECRET_STORE", "plaintext"), ("DEPLOYMENT_BUCKET", ""),
    ("EXISTING_TELEMETRY_QUEUE_ARN", "arn:aws:sqs:us-east-1:111111111111:existing"),
    ("USERS_TABLE", ""), ("INGEST_ROLE_ARN", ""),
])
def test_configuration_rejects_unsafe_or_incomplete_inputs(valid_env, field, value):
    valid_env[field] = value
    assert configuration_errors(valid_env)


def test_partial_existing_tables_require_explicit_name(valid_env):
    valid_env["USE_EXISTING_USERS_TABLE"] = "true"
    assert configuration_errors(valid_env)
    valid_env["USERS_TABLE"] = "approved-existing-users"
    assert configuration_errors(valid_env) == []


def test_existing_queues_require_matching_urls_and_arns(valid_env):
    valid_env.update(EXISTING_TELEMETRY_QUEUE_ARN="arn:aws:sqs:us-east-1:111111111111:queue",
                     EXISTING_TELEMETRY_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/111111111111/queue",
                     EXISTING_TELEMETRY_DLQ_ARN="arn:aws:sqs:us-east-1:111111111111:dlq",
                     EXISTING_TELEMETRY_DLQ_URL="https://sqs.us-east-1.amazonaws.com/111111111111/dlq")
    assert configuration_errors(valid_env) == []
    valid_env["EXISTING_TELEMETRY_QUEUE_URL"] += "-different"
    assert configuration_errors(valid_env)


def test_all_existing_tables_require_thirteen_unique_names(valid_env):
    valid_env["USE_EXISTING_TABLES"] = "true"
    valid_env.update({name: "existing-" + key.lower() for key, name in TABLE_ENV.items()})
    assert configuration_errors(valid_env) == []
    valid_env["USERS_TABLE"] = valid_env["MACHINES_TABLE"]
    assert configuration_errors(valid_env)


def test_preflight_detects_missing_handler_without_importing_it(tmp_path, monkeypatch):
    from scripts import validate_infra
    (tmp_path / "src").mkdir()
    (tmp_path / "src/present.py").write_text("raise RuntimeError('must not import')\ndef handler(event, context): pass\n")
    monkeypatch.setattr(validate_infra, "ROOT", tmp_path)
    monkeypatch.setattr(validate_infra, "function_definitions", lambda: {
        "present": {"handler": "src.present.handler"}, "pending": {"handler": "src.missing.handler"}})
    assert validate_infra.missing_handlers() == ["src.missing.handler"]


def test_workflows_are_bounded_and_preserve_local_plan_before_external_jobs():
    planning = yaml.safe_load((ROOT / "workflows/maintenance.asl.yml").read_text())
    incident = yaml.safe_load((ROOT / "workflows/incident.asl.yml").read_text())
    assert workflow_errors(planning) == workflow_errors(incident) == []
    states = planning["States"]
    assert states["AnalyzeLocal"]["Next"] == "ProjectPartsDemand"
    assert states["WaitLoad"]["Type"] == states["WaitQuery"]["Type"] == "Wait"
    for phase in ("LoadStatus", "QueryStatus"):
        assert any(choice.get("NumericGreaterThanEquals") == 20 for choice in states[phase]["Choices"])
    assert states["StartQuery"]["Parameters"]["action"] == "start_query"
    assert states["MarkAnalyticsDegraded"]["Parameters"]["action"] == "record_degradation"
    assert incident["States"]["CreateNotifications"]["Catch"][0]["Next"] == "NotificationDeliveryPending"
    assert incident["States"]["IsNewIncident"]["Choices"][0]["Next"] == "CreateNotifications"


def test_bad_state_transition_is_detected():
    assert workflow_errors({"StartAt": "Missing", "States": {"Start": {"Type": "Pass", "Next": "Missing"}}})


def test_seed_uids_and_local_configuration_are_not_packaged():
    names = [path.relative_to(ROOT).as_posix() for path in source_files()]
    assert "seed/demo_catalog.json" in names
    assert not any(name.startswith(("tests/", "frontend/", ".aws/", ".env")) for name in names)
    assert not any("demo_user_uids" in name or "credentials" in name for name in names)


def test_deployable_build_is_blocked_until_domain_handlers_exist(monkeypatch):
    monkeypatch.setattr("scripts.package_backend.missing_handlers", lambda: ["src.pending.handler"])
    with pytest.raises(ValueError, match="missing domain handlers"):
        build()


def test_deploy_does_not_call_aws_when_application_is_incomplete(valid_env, monkeypatch):
    from scripts import deploy
    monkeypatch.setattr(deploy, "environment", lambda: valid_env)
    monkeypatch.setattr(deploy, "missing_handlers", lambda: ["src.pending.handler"])
    monkeypatch.setattr(sys, "argv", ["deploy"])
    sdk = Mock(side_effect=AssertionError("No AWS calls expected"))
    monkeypatch.setattr(deploy, "session", sdk)
    assert deploy.main() == 1
    sdk.assert_not_called()


def test_template_only_artifact_is_explicitly_marked(tmp_path, monkeypatch):
    from scripts import package_backend
    (tmp_path / "requirements.txt").write_text("boto3==1.40.0\n")
    monkeypatch.setattr(package_backend, "ROOT", tmp_path)
    monkeypatch.setattr(package_backend, "source_files", lambda: [])
    monkeypatch.setattr(package_backend, "missing_handlers", lambda: ["src.missing.handler"])
    path = package_backend.build(template_only=True)
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("__arquifusion_build__.json"))
    assert manifest["template_only"] is True
    assert manifest["missing_handlers"] == ["src.missing.handler"]


def test_serverless_guard_blocks_template_artifact_even_with_template_flag(tmp_path):
    artifact_dir = tmp_path / ".artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "build-manifest.json").write_text(json.dumps({"template_only": True, "missing_handlers": []}))
    harness = """
const child = require('node:child_process');
child.spawnSync = () => ({status: 0});
const Guard = require(process.argv[1]);
const guard = new Guard({serviceDir: process.argv[2], processedInput: {commands: ['deploy']},
  configSchemaHandler: {schema: {definitions: {awsLambdaRuntime: {enum: ['python3.11']}}}}});
try { guard.hooks.initialize(); process.exit(2); }
catch (error) { console.log(error.message); process.exit(error.message.includes('Template-only artifacts') ? 0 : 3); }
"""
    result = subprocess.run(["node", "-e", harness, str(ROOT / "scripts/serverless-guard.cjs"), str(tmp_path)],
                            env=dict(os.environ, AF_TEMPLATE_ONLY="1"), capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not (ROOT / ".artifacts/template-only/cloudformation-template-update-stack.json").exists(),
                    reason="Run npm run validate:template to generate the real compiled template")
def test_actual_serverless_template_uses_lab_roles_and_single_integrations():
    template = json.loads((ROOT / ".artifacts/template-only/cloudformation-template-update-stack.json").read_text())
    resources = template["Resources"]
    assert not any(row["Type"].startswith("AWS::IAM::") for row in resources.values())
    functions = [row for row in resources.values() if row["Type"] == "AWS::Lambda::Function"]
    assert len(functions) == 14
    assert all(row["Properties"]["Runtime"] == "python3.12" for row in functions)
    assert sum(row["Type"] == "AWS::ApiGatewayV2::Api" for row in resources.values()) == 1
    assert sum(row["Type"] == "AWS::Lambda::EventSourceMapping" for row in resources.values()) == 1
    authorizer = next(row["Properties"] for row in resources.values() if row["Type"] == "AWS::ApiGatewayV2::Authorizer")
    assert authorizer["AuthorizerPayloadFormatVersion"] == "2.0"
    assert authorizer["EnableSimpleResponses"] is True
    assert authorizer["AuthorizerResultTtlInSeconds"] == 0
    routes = [row["Properties"] for row in resources.values() if row["Type"] == "AWS::ApiGatewayV2::Route"]
    assert len(routes) == len({row["RouteKey"] for row in routes}) == 18
    telemetry = next(row for row in routes if row["RouteKey"] == "POST /telemetry/batch")
    assert telemetry.get("AuthorizationType", "NONE") == "NONE"
    assert "AuthorizerId" not in telemetry
    assert all(row["AuthorizationType"] == "CUSTOM" for row in routes if "/api/" in row["RouteKey"])
    assert not any(row["RouteKey"].startswith("OPTIONS ") for row in routes)
    assert all(row["Properties"]["State"] == "DISABLED" for row in resources.values() if row["Type"] == "AWS::Scheduler::Schedule")
