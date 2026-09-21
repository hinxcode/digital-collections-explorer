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
echo "$*" >> "$FAKE_AWS_LOG"
case "$*" in
*"sts get-caller-identity"*) echo "123456789012" ;;
*"describe-stacks"*"InstanceId"*)
    [ "$FAKE_STACK_EXISTS" = "true" ] || exit 255
    echo "i-0existing" ;;
*"describe-stacks"*"DiskSizeGiB"*) echo "40" ;;
*"describe-instances"*"InstanceType"*) echo "c7i.2xlarge" ;;
*"describe-instances"*) echo "ami-0existing111" ;;
*"ssm send-command"*)
    echo "$*" > "$FAKE_AWS_LOG.last_command"
    echo "command-1" ;;
*"ssm get-command-invocation"*)
    if grep -q -- "--json" "$FAKE_AWS_LOG.last_command"; then
        [ "$FAKE_MACHINE" = "current" ] || { printf 'Failed\t'; exit 0; }
        printf 'Success\t{"indexed": 3, "run": {"active_seconds": 60}}'
    else
        printf 'Success\tIndexing: finished'
    fi ;;
*"ssm get-parameter"*) echo "ami-0latest999" ;;
*"cloudformation deploy"*)
    if [ -n "$FAKE_OVERWRITE_SCRIPT" ]; then
        { head -c 3000 /dev/zero | tr '\0' '#'; echo; cat "$FAKE_OVERWRITE_SCRIPT"; } > "$FAKE_OVERWRITE_SCRIPT.new"
        cat "$FAKE_OVERWRITE_SCRIPT.new" > "$FAKE_OVERWRITE_SCRIPT"
    fi
    echo "Successfully created/updated stack" ;;
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

    def run(
        stack_exists,
        *extra,
        overwrite_while_running=False,
        script="deploy.sh",
        machine="current",
    ):
        import os

        log.write_text("")
        env = {
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_AWS_LOG": str(log),
            "FAKE_STACK_EXISTS": "true" if stack_exists else "false",
            "FAKE_OVERWRITE_SCRIPT": (
                str(scripts / "deploy.sh") if overwrite_while_running else ""
            ),
            "FAKE_MACHINE": machine,
        }
        if script != "deploy.sh":
            command = ["bash", str(scripts / script), "demo", *extra]
            return subprocess.run(command, capture_output=True, text=True, env=env), []
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


def test_script_survives_being_saved_while_it_waits_for_aws(fake_deploy):
    result, deploys = fake_deploy(False, overwrite_while_running=True)
    assert result.returncode == 0, result.stderr
    assert "command not found" not in result.stderr
    assert "SiteUrl" in result.stdout


@pytest.fixture(scope="module")
def run_cost():
    import sys

    sys.path.insert(0, str(ROOT / "deploy" / "aws"))
    path = ROOT / "deploy" / "aws" / "run_cost.py"
    spec = importlib.util.spec_from_file_location("run_cost", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRICES = {"c7i.2xlarge": 0.357, "t3.medium": 0.0416}
FINISHED_REPORT = {
    "indexed": 20481,
    "run": {
        "active_seconds": 5400,
        "machine_type": "c7i.2xlarge",
        "finished_at": "2026-09-20T20:00:00Z",
    },
}


def test_indexing_is_priced_per_run_and_per_thousand_images(run_cost):
    lines = run_cost.cost_lines(FINISHED_REPORT, "t3.medium", None, PRICES.get)
    text = "\n".join(lines)
    assert "Indexing cost about $0.54" in text
    assert "1.5 hours on c7i.2xlarge" in text
    assert "$0.026 per 1,000 images" in text
    assert "WARNING" not in text


def test_a_large_machine_left_running_after_indexing_is_pointed_out(run_cost):
    from datetime import datetime, timezone

    now = datetime(2026, 9, 21, 1, 0, tzinfo=timezone.utc)
    lines = run_cost.cost_lines(FINISHED_REPORT, "c7i.2xlarge", None, PRICES.get, now)
    warning = [line for line in lines if line.startswith("WARNING")][0]
    assert "finished 5 hours ago" in warning
    assert "$230.24 per month" in warning
    assert "--instance-type t3.medium" in warning


def test_an_unrecorded_indexing_machine_can_be_named_by_hand(run_cost):
    report = {"indexed": 10, "run": {"active_seconds": 3600, "machine_type": None}}
    unknown = run_cost.cost_lines(report, "t3.medium", None, PRICES.get)
    assert any("--indexed-on" in line for line in unknown)
    named = run_cost.cost_lines(report, "t3.medium", "c7i.2xlarge", PRICES.get)
    assert any("Indexing cost about $0.36" in line for line in named)


def test_status_prices_the_run_when_the_machine_can_report_it(fake_deploy):
    result, _ = fake_deploy(True, script="status.sh")
    assert result.returncode == 0, result.stderr
    assert "c7i.2xlarge" in result.stdout
    assert "(cost estimate)" in result.stdout


def test_status_says_how_to_update_a_machine_too_old_to_report(fake_deploy):
    result, _ = fake_deploy(True, script="status.sh", machine="old")
    assert result.returncode == 0, result.stderr
    assert "older version" in result.stdout
    assert "update.sh demo" in result.stdout


def test_update_refreshes_the_bootstrap_script_before_switching_images(fake_deploy):
    result, _ = fake_deploy(True, "--image", "example/image:2", script="update.sh")
    assert result.returncode == 0, result.stderr
    assert "The index and the address are kept" in result.stdout
