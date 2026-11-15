"""Compile an offline CloudFormation template with non-deployable, marked artifacts."""
from __future__ import annotations

import os
import subprocess
import sys

from scripts.aws_config import ROOT, TABLE_ENV
from scripts.package_backend import build


def main() -> int:
    build(template_only=True)
    env = dict(os.environ)
    # These placeholders exist only in this child process. No AWS credentials are fabricated.
    env.update({"AF_TEMPLATE_ONLY": "1", "PYTHON": sys.executable, "SLS_TELEMETRY_DISABLED": "1",
                "EXPECTED_AWS_ACCOUNT_ID": "111111111111", "DEPLOYMENT_BUCKET": "af-offline-validation-artifacts",
                "PAGES_ORIGIN": "https://offline-validation.pages.dev", "FIREBASE_PROJECT_ID": "offline-validation",
                "LAMBDA_ROLE_ARN": "arn:aws:iam::111111111111:role/OfflineValidationOnly",
                "SFN_ROLE_ARN": "arn:aws:iam::111111111111:role/OfflineValidationOnly",
                "EVENTS_START_SFN_ROLE_ARN": "arn:aws:iam::111111111111:role/OfflineValidationOnly",
                "SCHEDULER_ROLE_ARN": "arn:aws:iam::111111111111:role/OfflineValidationOnly",
                "SIMULATOR_ROLE_ARN": "arn:aws:iam::111111111111:role/OfflineValidationOnly",
                "INGEST_ROLE_ARN": "arn:aws:iam::111111111111:role/OfflineValidationOnly",
                "ENABLE_SCHEDULER": "false", "ENABLE_TELEMETRY_CONSUMER": "false", "ENABLE_ALARMS": "true",
                "USE_EXISTING_TABLES": "false", "DEMO_SEED_ENABLED": "false", "DEMO_USER_UIDS_JSON": "{}",
                "DEMO_OPERATION_ID": "op-demo", "SECRET_STORE": "ssm", "SIMULATOR_SECRET_ID": "/af/dev/simulator-token",
                "GCP_CREDENTIALS_SECRET_ID": "", "GCP_PROJECT_ID": "offline-validation", "BQ_DATASET": "arquifusion_dev", "BQ_LOCATION": "US"})
    for variable in TABLE_ENV.values():
        env[variable] = "af-dev-t-" + variable.removesuffix("_TABLE").lower().replace("_", "-")
        env["USE_EXISTING_" + variable] = "false"
    for variable in ("EXISTING_TELEMETRY_BUCKET", "EXISTING_TELEMETRY_QUEUE_ARN", "EXISTING_TELEMETRY_QUEUE_URL",
                     "EXISTING_TELEMETRY_DLQ_ARN", "EXISTING_TELEMETRY_DLQ_URL"):
        env[variable] = ""
    result = subprocess.run(["node", str(ROOT / "node_modules/serverless/bin/serverless.js"), "package",
                             "--stage", "dev", "--region", "us-east-1", "--package", ".artifacts/template-only"],
                            cwd=ROOT, env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
