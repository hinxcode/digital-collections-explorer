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
