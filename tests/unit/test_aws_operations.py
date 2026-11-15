from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
from unittest.mock import Mock

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
import pytest

from scripts.manage_schedules import change_state
from scripts.redrive_telemetry import inspect_pair, start_redrive
from scripts.smoke_aws import run_checks
from src.common.secrets import read_json_secret, read_secret


ACCOUNT = "111111111111"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/AuthorizedLabRole"
QUEUE = f"https://sqs.us-east-1.amazonaws.com/{ACCOUNT}/telemetry"
DLQ = f"https://sqs.us-east-1.amazonaws.com/{ACCOUNT}/telemetry-dlq"
QUEUE_ARN = f"arn:aws:sqs:us-east-1:{ACCOUNT}:telemetry"
DLQ_ARN = f"arn:aws:sqs:us-east-1:{ACCOUNT}:telemetry-dlq"


def client(service):
    return boto3.client(service, region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")


def test_ssm_reader_requires_decryption_and_secure_string():
    ssm = client("ssm")
    with Stubber(ssm) as stub:
        stub.add_response("get_parameter", {"Parameter": {"Name": "/af/dev/simulator-token", "Type": "SecureString", "Value": "synthetic-secret"}},
                          {"Name": "/af/dev/simulator-token", "WithDecryption": True})
        assert read_secret("/af/dev/simulator-token", client=ssm) == "synthetic-secret"


def test_plaintext_ssm_parameter_is_rejected():
    ssm = client("ssm")
    with Stubber(ssm) as stub:
        stub.add_response("get_parameter", {"Parameter": {"Type": "String", "Value": "test"}}, {"Name": "test", "WithDecryption": True})
        with pytest.raises(ValueError, match="SecureString"):
            read_secret("test", client=ssm)


def test_secretsmanager_json_is_loaded_only_at_runtime():
    secrets = client("secretsmanager")
    with Stubber(secrets) as stub:
        stub.add_response("get_secret_value", {"SecretString": '{"producer_id":"demo"}'}, {"SecretId": "/af/dev/simulator-token"})
        assert read_json_secret("/af/dev/simulator-token", store="secretsmanager", client=secrets) == {"producer_id": "demo"}


def test_secret_permissions_failure_is_propagated():
    ssm = client("ssm")
    with Stubber(ssm) as stub:
        stub.add_client_error("get_parameter", service_error_code="AccessDeniedException", expected_params={"Name": "test", "WithDecryption": True})
        with pytest.raises(ClientError):
            read_secret("test", client=ssm)


def test_redrive_validates_pair_and_uses_native_move_without_receiving_payloads():
    sqs = client("sqs")
    with Stubber(sqs) as stub:
        stub.add_response("get_queue_attributes", {"Attributes": {"QueueArn": QUEUE_ARN, "RedrivePolicy": json.dumps({"deadLetterTargetArn": DLQ_ARN})}},
                          {"QueueUrl": QUEUE, "AttributeNames": ["QueueArn", "RedrivePolicy"]})
        stub.add_response("get_queue_attributes", {"Attributes": {"QueueArn": DLQ_ARN, "ApproximateNumberOfMessages": "2"}},
                          {"QueueUrl": DLQ, "AttributeNames": ["QueueArn", "ApproximateNumberOfMessages"]})
        stub.add_response("start_message_move_task", {"TaskHandle": "test-move-task"},
                          {"SourceArn": DLQ_ARN, "DestinationArn": QUEUE_ARN, "MaxNumberOfMessagesPerSecond": 1})
        pair = inspect_pair(sqs, QUEUE, DLQ, expected_account=ACCOUNT)
        assert pair["visible_messages"] == 2
        assert start_redrive(sqs, pair, rate=1)["TaskHandle"] == "test-move-task"


def test_redrive_rejects_a_dlq_not_attached_to_source():
    sqs = Mock()
    sqs.get_queue_attributes.side_effect = [
        {"Attributes": {"QueueArn": QUEUE_ARN, "RedrivePolicy": json.dumps({"deadLetterTargetArn": "another-dlq"})}},
        {"Attributes": {"QueueArn": DLQ_ARN}},
    ]
    with pytest.raises(ValueError, match="not configured"):
        inspect_pair(sqs, QUEUE, DLQ, expected_account=ACCOUNT)
    sqs.start_message_move_task.assert_not_called()


def test_redrive_rejects_another_account():
    sqs = Mock()
    sqs.get_queue_attributes.side_effect = [{"Attributes": {"QueueArn": QUEUE_ARN}}, {"Attributes": {"QueueArn": DLQ_ARN}}]
    with pytest.raises(ValueError, match="account"):
        inspect_pair(sqs, QUEUE, DLQ, expected_account="222222222222")


@pytest.mark.parametrize("rate", [0, 11])
def test_redrive_rate_is_bounded(rate):
    with pytest.raises(ValueError):
        start_redrive(Mock(), {}, rate=rate)


def test_pause_schedule_preserves_target_input_role_and_expression():
    scheduler = client("scheduler")
    target = {"Arn": f"arn:aws:lambda:us-east-1:{ACCOUNT}:function:af-dev-simulate-telemetry", "RoleArn": ROLE, "Input": '{"run_id":"stable"}'}
    response = {"Name": "af-dev-simulate-telemetry", "State": "ENABLED", "ScheduleExpression": "rate(1 minute)",
                "FlexibleTimeWindow": {"Mode": "OFF"}, "Target": target,
                "Arn": f"arn:aws:scheduler:us-east-1:{ACCOUNT}:schedule/default/af-dev-simulate-telemetry",
                "CreationDate": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    expected = {key: value for key, value in response.items() if key not in {"Arn", "CreationDate"}}
    expected["State"] = "DISABLED"
    with Stubber(scheduler) as stub:
        stub.add_response("get_schedule", response, {"Name": "af-dev-simulate-telemetry"})
        stub.add_response("update_schedule", {"ScheduleArn": response["Arn"]}, expected)
        assert change_state(scheduler, "af-dev-simulate-telemetry", "DISABLED", apply=True)["applied"] is True


def test_schedule_default_mode_does_not_update():
    scheduler = Mock()
    scheduler.get_schedule.return_value = {"State": "ENABLED"}
    assert change_state(scheduler, "af-dev-simulate-telemetry", "DISABLED")["applied"] is False
    scheduler.update_schedule.assert_not_called()


def fake_aws():
    aws = Mock(region_name="us-east-1")
    clients = {name: Mock() for name in ("sts", "cloudformation", "s3", "iam")}
    aws.client.side_effect = clients.__getitem__
    clients["sts"].get_caller_identity.return_value = {"Account": ACCOUNT, "Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/voclabs/private-session-name"}
    clients["s3"].head_bucket.return_value = {}
    clients["s3"].get_bucket_location.return_value = {"LocationConstraint": None}
    clients["s3"].get_public_access_block.return_value = {"PublicAccessBlockConfiguration": {
        key: True for key in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")}}
    clients["iam"].get_role.return_value = {"Role": {"Arn": ROLE, "AssumeRolePolicyDocument": {"Statement": [{
        "Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {"Service": ["lambda.amazonaws.com", "states.amazonaws.com", "events.amazonaws.com"]},
    }]}}}
    return aws, clients


def smoke_env():
    return {"EXPECTED_AWS_ACCOUNT_ID": ACCOUNT, "DEPLOYMENT_BUCKET": "af-test-artifacts",
            **{name: ROLE for name in ("LAMBDA_ROLE_ARN", "SFN_ROLE_ARN", "EVENTS_START_SFN_ROLE_ARN")}}


def test_smoke_reads_do_not_claim_deployment_permissions_or_print_session_identity():
    aws, clients = fake_aws()
    report = run_checks(smoke_env(), aws)
    assert report["status"] == "READ_CHECKS_PASSED"
    assert report["effective_deployment_permissions"] == "NOT_VERIFIED"
    assert report["actor_role"] == "voclabs"
    assert "private-session-name" not in json.dumps(report)
    clients["s3"].put_object.assert_not_called()
    clients["s3"].delete_object.assert_not_called()


def test_wrong_account_blocks_all_other_probes():
    aws, clients = fake_aws()
    env = smoke_env()
    env["EXPECTED_AWS_ACCOUNT_ID"] = "222222222222"
    assert run_checks(env, aws)["status"] == "BLOCKED"
    clients["cloudformation"].list_stacks.assert_not_called()
    clients["s3"].head_bucket.assert_not_called()


def test_s3_write_probe_cleans_up_exact_version_even_when_read_is_denied():
    aws, clients = fake_aws()
    s3 = clients["s3"]
    s3.put_object.return_value = {"VersionId": "test-version"}
    s3.get_object.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": "sensitive-error-detail"}}, "GetObject")
    report = run_checks(smoke_env(), aws, write_test=True)
    key = s3.put_object.call_args.kwargs["Key"]
    s3.delete_object.assert_called_once_with(Bucket="af-test-artifacts", Key=key, ExpectedBucketOwner=ACCOUNT, VersionId="test-version")
    assert report["status"] == "PARTIAL"
    assert "sensitive-error-detail" not in json.dumps(report)


def test_s3_probe_uses_unique_key_and_checks_readback():
    aws, clients = fake_aws()
    clients["s3"].put_object.return_value = {}
    clients["s3"].get_object.return_value = {"Body": BytesIO(b"ArquiFusion AWS-01 synthetic permissions check\n")}
    assert run_checks(smoke_env(), aws, write_test=True)["status"] == "READ_CHECKS_PASSED"
    assert clients["s3"].put_object.call_args.kwargs["Key"].startswith("serverless/arquifusion/dev/aws-01/")


def test_trust_without_assume_role_action_is_not_reported_as_verified():
    aws, clients = fake_aws()
    clients["iam"].get_role.return_value["Role"]["AssumeRolePolicyDocument"]["Statement"][0]["Action"] = "unrelated:Action"
    assert run_checks(smoke_env(), aws)["status"] == "PARTIAL"
