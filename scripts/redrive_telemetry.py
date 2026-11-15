"""Inspect telemetry DLQ metadata, or explicitly start a native SQS redrive task."""
from __future__ import annotations

import argparse
import json

from scripts.aws_config import environment, verified_session


def inspect_pair(sqs, source_url: str, dlq_url: str, *, expected_account: str) -> dict:
    source = sqs.get_queue_attributes(QueueUrl=source_url, AttributeNames=["QueueArn", "RedrivePolicy"])["Attributes"]
    dead = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn", "ApproximateNumberOfMessages"])["Attributes"]
    source_arn, dlq_arn = source["QueueArn"], dead["QueueArn"]
    if not expected_account or any(arn.split(":")[4] != expected_account for arn in (source_arn, dlq_arn)):
        raise ValueError("Queue account does not match the verified account")
    if source_arn == dlq_arn or source_arn.endswith(".fifo") or dlq_arn.endswith(".fifo"):
        raise ValueError("Expected a distinct Standard source queue and DLQ")
    if json.loads(source.get("RedrivePolicy", "{}" )).get("deadLetterTargetArn") != dlq_arn:
        raise ValueError("The source queue is not configured to use this DLQ")
    return {"source_arn": source_arn, "dlq_arn": dlq_arn, "visible_messages": int(dead.get("ApproximateNumberOfMessages", "0"))}


def start_redrive(sqs, pair: dict, *, rate: int) -> dict:
    if not 1 <= rate <= 10:
        raise ValueError("Demo redrive rate must be between 1 and 10 messages/second")
    return sqs.start_message_move_task(SourceArn=pair["dlq_arn"], DestinationArn=pair["source_arn"],
                                      MaxNumberOfMessagesPerSecond=rate)


def main() -> int:
    env = environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-url", required=True)
    parser.add_argument("--dlq-url", required=True)
    parser.add_argument("--execute", action="store_true", help="Move all messages from this DLQ after correcting the cause")
    parser.add_argument("--status", action="store_true", help="List recent move tasks instead of starting one")
    parser.add_argument("--rate", type=int, default=1)
    args = parser.parse_args()
    if args.execute and args.status:
        parser.error("Choose --execute or --status")
    sqs = verified_session(env).client("sqs")
    pair = inspect_pair(sqs, args.queue_url, args.dlq_url, expected_account=env.get("EXPECTED_AWS_ACCOUNT_ID", ""))
    if args.status:
        tasks = sqs.list_message_move_tasks(SourceArn=pair["dlq_arn"], MaxResults=10)
        rows = [{key: row[key] for key in ("Status", "ApproximateNumberOfMessagesMoved", "ApproximateNumberOfMessagesToMove", "StartTime") if key in row}
                for row in tasks.get("Results", [])]
        print(json.dumps({"tasks": rows}, indent=2))
    elif args.execute:
        result = start_redrive(sqs, pair, rate=args.rate)
        print(json.dumps({"status": "STARTED", "task_handle": result["TaskHandle"]}))
    else:
        print(json.dumps({"status": "INSPECT_ONLY", **pair}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
