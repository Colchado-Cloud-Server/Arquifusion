"""List, enable or pause the two demo schedules without changing their targets."""
from __future__ import annotations

import argparse
import json

from scripts.aws_config import environment, verified_session


def change_state(client, name: str, state: str, *, apply: bool = False) -> dict:
    if state not in {"ENABLED", "DISABLED"}:
        raise ValueError("Unknown schedule state")
    current = client.get_schedule(Name=name)
    if apply and current["State"] != state:
        accepted = client.meta.service_model.operation_model("UpdateSchedule").input_shape.members
        update = {key: value for key, value in current.items() if key in accepted}
        update["State"] = state
        client.update_schedule(**update)
    return {"name": name, "previous_state": current["State"], "requested_state": state, "applied": apply}


def main() -> int:
    env = environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=["ENABLED", "DISABLED"], default="DISABLED")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    client = verified_session(env).client("scheduler")
    stage = env.get("STAGE", "dev")
    report = [change_state(client, f"af-{stage}-{name}", args.state, apply=args.apply)
              for name in ("simulate-telemetry", "maintenance-planning")]
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
