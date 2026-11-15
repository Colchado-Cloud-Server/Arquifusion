"""Build the shared Lambda ZIP with Linux wheels and an explicit source allowlist."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from scripts.aws_config import ROOT
from scripts.validate_infra import missing_handlers


def source_files() -> list[Path]:
    files = list((ROOT / "src").rglob("*.py"))
    files += [path for path in (ROOT / "contracts").rglob("*") if path.is_file()
              and (path.name.endswith(".schema.json") or path.name in {"openapi.yml", "openapi.yaml"})]
    files += list((ROOT / "sql").rglob("*.sql"))
    for name in ("demo_catalog.json", "telemetry_scenarios.json"):
        if (ROOT / "seed" / name).is_file():
            files.append(ROOT / "seed" / name)
    return sorted(files)


def source_digest() -> str:
    digest = hashlib.sha256()
    for path in source_files() + [ROOT / "requirements.txt"]:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def build(*, template_only: bool = False) -> Path:
    missing = missing_handlers()
    if missing and not template_only:
        raise ValueError("Cannot build deployable backend: missing domain handlers")
    output = ROOT / ".artifacts"
    output.mkdir(exist_ok=True)
    artifact = output / "backend.zip"
    manifest = {"template_only": template_only, "missing_handlers": missing, "source_digest": source_digest(),
                "runtime": "python3.12", "architecture": "x86_64"}
    with TemporaryDirectory(prefix="backend-", dir=output) as directory:
        staging = Path(directory)
        if not template_only:
            subprocess.run([
                sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                "--timeout", "15", "--retries", "0", "--no-compile", "--only-binary=:all:",
                "--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_28_x86_64",
                "--implementation", "cp", "--python-version", "3.12", "--abi", "cp312",
                "--target", str(staging), "-r", str(ROOT / "requirements.txt"),
            ], check=True)
        with ZipFile(artifact, "w", ZIP_DEFLATED) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, path.relative_to(staging).as_posix())
            for path in source_files():
                archive.write(path, path.relative_to(ROOT).as_posix())
            archive.writestr("__arquifusion_build__.json", json.dumps(manifest))
    manifest["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (output / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-only", action="store_true")
    args = parser.parse_args()
    try:
        print(build(template_only=args.template_only))
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
