import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def estimate_cost():
    path = ROOT / "deploy" / "aws" / "estimate_cost.py"
    spec = importlib.util.spec_from_file_location("estimate_cost", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_estimate_adds_up_the_monthly_parts(estimate_cost):
    costs = {"machine": 30.0, "machine_hour": 0.04, "disk": 2.5, "address": 3.5}
    text = estimate_cost.render(costs, "t3.medium", 30, "us-west-2")
    assert "$36.00" in text


def test_estimate_never_shows_a_total_it_cannot_back_up(estimate_cost):
    costs = {"machine": None, "machine_hour": None, "disk": 2.5, "address": 3.5}
    text = estimate_cost.render(costs, "t3.medium", 30, "us-west-2")
    assert "price not found" in text
    assert "Total per month" not in text


@pytest.mark.parametrize(
    "script",
    ["deploy/bootstrap.sh", "deploy/aws/deploy.sh", "deploy/aws/status.sh"],
)
def test_scripts_parse_and_explain_themselves(script):
    path = ROOT / script
    assert subprocess.run(["bash", "-n", str(path)]).returncode == 0
    assert path.stat().st_mode & 0o111, f"{script} must be executable"


def test_bootstrap_rejects_unsafe_collection_names():
    result = subprocess.run(
        ["bash", str(ROOT / "deploy/bootstrap.sh"), "status", "--name", "Bad Name!"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "lowercase" in result.stderr


def test_deploy_never_prints_the_full_account_id():
    script = (ROOT / "deploy/aws/deploy.sh").read_text()
    printed = [
        line for line in script.splitlines() if "echo" in line and "ACCOUNT" in line
    ]
    assert printed, "the account should still be identified to the person deploying"
    assert all("${ACCOUNT: -4}" in line for line in printed)


FAKE_AWS = r"""#!/usr/bin/env bash
# Stands in for the AWS CLI: records every call and answers like a real account.
echo "$*" >> "$FAKE_AWS_LOG"
case "$*" in
*"sts get-caller-identity"*) echo "123456789012" ;;
*"describe-stacks"*"InstanceId"*)
    [ "$FAKE_STACK_EXISTS" = "true" ] || exit 255
    echo "i-0existing" ;;
*"describe-stacks"*"DiskSizeGiB"*) echo "40" ;;
*"describe-instances"*) echo "ami-0existing111" ;;
*"ssm get-parameter"*) echo "ami-0latest999" ;;
*"cloudformation deploy"*) echo "Successfully created/updated stack" ;;
*) echo "SiteUrl http://203.0.113.10" ;;
esac
"""


@pytest.fixture()
def fake_deploy(tmp_path):
    import shutil

    scripts = tmp_path / "deploy" / "aws"
    shutil.copytree(ROOT / "deploy" / "aws", scripts)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "aws").write_text(FAKE_AWS)
    (fake_bin / "aws").chmod(0o755)
    (fake_bin / "python3").write_text("#!/usr/bin/env bash\necho '  (cost estimate)'\n")
    (fake_bin / "python3").chmod(0o755)
    log = tmp_path / "aws.log"

    def run(stack_exists, *extra):
        import os

        log.write_text("")
        env = {
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_AWS_LOG": str(log),
            "FAKE_STACK_EXISTS": "true" if stack_exists else "false",
        }
        command = ["bash", str(scripts / "deploy.sh"), "demo", "--yes"]
        command += ["--source", "s3://bucket/images", "--disk-gib", "40", *extra]
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        deploys = [
            c for c in log.read_text().splitlines() if "cloudformation deploy" in c
        ]
        return result, deploys

    return run


def test_new_deployment_pins_the_latest_machine_image(fake_deploy):
    result, deploys = fake_deploy(False)
    assert result.returncode == 0, result.stderr
    assert "MachineImageId=ami-0latest999" in deploys[0]


def test_update_keeps_the_image_the_machine_already_runs(fake_deploy):
    result, deploys = fake_deploy(True, "--instance-type", "t3.medium")
    assert result.returncode == 0, result.stderr
    assert "MachineImageId=ami-0existing111" in deploys[0]
    assert "ami-0latest999" not in deploys[0]
    assert "InstanceType=t3.medium" in deploys[0]
    assert "updated in place" in result.stdout


def test_update_refuses_to_change_the_disk_because_that_deletes_the_index(fake_deploy):
    result, deploys = fake_deploy(True, "--disk-gib", "80")
    assert result.returncode != 0
    assert deploys == []
    assert "delete its index" in result.stderr
