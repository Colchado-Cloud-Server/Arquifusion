"""Deploy only a complete backend, in the explicitly verified lab account."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from scripts.aws_config import ROOT, configuration_errors, environment, session
from scripts.package_backend import build
from scripts.validate_infra import missing_handlers, static_errors


def main() -> int:
    env = environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default=env.get("STAGE", "dev"))
    parser.add_argument("--region", default=env.get("AWS_REGION", "us-east-1"))
    args = parser.parse_args()
    env.update(STAGE=args.stage, AWS_REGION=args.region, PYTHON=sys.executable)
    errors = configuration_errors(env) + static_errors()
    missing = missing_handlers()
    if missing:
        errors.append("Missing handlers: " + ", ".join(missing))
    if errors:
        print(json.dumps({"status": "BLOCKED", "errors": errors}, indent=2))
        return 1
    aws = session(env, region=args.region)
    identity = aws.client("sts").get_caller_identity()
    if identity["Account"] != env["EXPECTED_AWS_ACCOUNT_ID"]:
        raise RuntimeError("Deployment blocked: active AWS account does not match EXPECTED_AWS_ACCOUNT_ID")
    aws.client("s3").head_bucket(Bucket=env["DEPLOYMENT_BUCKET"], ExpectedBucketOwner=identity["Account"])
    os.environ.update(env)
    os.environ.pop("AF_TEMPLATE_ONLY", None)
    build()
    cli = ["node", str(ROOT / "node_modules/serverless/bin/serverless.js")]
    flags = ["--stage", args.stage, "--region", args.region]
    subprocess.run(cli + ["package"] + flags, cwd=ROOT, env=dict(os.environ), check=True)
    subprocess.run(cli + ["deploy", "--package", ".serverless"] + flags, cwd=ROOT, env=dict(os.environ), check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
