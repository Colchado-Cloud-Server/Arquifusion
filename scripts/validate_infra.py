"""Static checks; --template-only permits absent domain handlers without authorizing deployment."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json

import yaml

from scripts.aws_config import ROOT, configuration_errors, environment, function_definitions, verified_session


def missing_handlers() -> list[str]:
    missing = []
    for function in function_definitions().values():
        handler = function["handler"]
        module, symbol = handler.rsplit(".", 1)
        path = ROOT / (module.replace(".", "/") + ".py")
        if not path.is_file():
            missing.append(handler)
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol for node in tree.body):
            missing.append(handler)
    return missing


def workflow_errors(definition: dict) -> list[str]:
    states = definition.get("States", {})
    errors = []
    if definition.get("StartAt") not in states:
        errors.append("Invalid StartAt")
    for name, state in states.items():
        targets = ([state["Next"]] if "Next" in state else []) + ([state["Default"]] if "Default" in state else [])
        targets += [choice["Next"] for choice in state.get("Choices", [])]
        targets += [catch["Next"] for catch in state.get("Catch", [])]
        for target in targets:
            if target not in states:
                errors.append(f"{name}: unknown transition {target}")
        if state.get("Type") == "Task" and not state.get("Retry"):
            errors.append(f"{name}: Lambda task requires bounded retries")
    return errors


def static_errors() -> list[str]:
    errors = []
    resources = {}
    for path in (ROOT / "infra").glob("*.yml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, resource in (document or {}).get("Resources", {}).items():
            if name in resources:
                errors.append(f"Duplicate resource owner: {name}")
            resources[name] = resource
            if resource.get("Type", "").startswith("AWS::IAM::"):
                errors.append(f"{name}: infrastructure must reference existing lab roles")
    queues = resources.get("TelemetryQueue", {}).get("Properties", {})
    timeout = function_definitions()["processTelemetry"].get("timeout", 30)
    if queues.get("VisibilityTimeout", 0) < 6 * timeout:
        errors.append("SQS visibility timeout is below six times the consumer timeout")
    mappings = [r for r in resources.values() if r["Type"] == "AWS::Lambda::EventSourceMapping"]
    if len(mappings) != 1 or mappings[0]["Properties"].get("FunctionResponseTypes") != ["ReportBatchItemFailures"]:
        errors.append("Exactly one telemetry mapping with partial failure reporting is required")
    for path in (ROOT / "workflows").glob("*.asl.yml"):
        errors += [f"{path.name}: {error}" for error in workflow_errors(yaml.safe_load(path.read_text()))]
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-only", action="store_true")
    parser.add_argument("--check-artifact", action="store_true")
    parser.add_argument("--verify-account", action="store_true", help="Check the current AWS session before a real deployment")
    args = parser.parse_args()
    errors = static_errors()
    if not args.template_only:
        errors += configuration_errors(environment())
    missing = missing_handlers()
    if missing and not args.template_only:
        errors.append("Domain handlers are missing; deployment is blocked")
    if args.check_artifact:
        from scripts.package_backend import source_digest
        try:
            manifest = json.loads((ROOT / ".artifacts/build-manifest.json").read_text())
            artifact = ROOT / ".artifacts/backend.zip"
            if manifest["template_only"] or manifest["missing_handlers"]:
                errors.append("Template-only artifacts cannot be deployed")
            if manifest["source_digest"] != source_digest():
                errors.append("Source changed after packaging; rebuild the artifact")
            if manifest["artifact_sha256"] != hashlib.sha256(artifact.read_bytes()).hexdigest():
                errors.append("Artifact hash does not match its build manifest")
        except (OSError, ValueError, KeyError):
            errors.append("A verified deployable build manifest is required")
    if args.verify_account and not errors:
        try:
            verified_session(environment())
        except Exception:
            errors.append("AWS session could not be verified against EXPECTED_AWS_ACCOUNT_ID")
    print(json.dumps({"status": "BLOCKED" if errors else ("TEMPLATE_ONLY" if args.template_only else "READY"),
                      "errors": errors, "missing_handlers": missing}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
