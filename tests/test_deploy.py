import base64
import importlib.util
import json
import subprocess
import sys
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
    [
        "deploy/bootstrap.sh",
        "deploy/aws/deploy.sh",
        "deploy/aws/status.sh",
        "deploy/aws/update.sh",
        "deploy/aws/describe.sh",
    ],
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
    [ "$FAKE_STACK_EXISTS" = "true" ] || grep -q "cloudformation deploy" "$FAKE_AWS_LOG" || exit 255
    echo "i-0existing" ;;
*"describe-stacks"*"DiskSizeGiB"*) echo "40" ;;
*"describe-instances"*"InstanceType"*) echo "c7i.2xlarge" ;;
*"describe-instances"*) echo "ami-0existing111" ;;
*"ssm send-command"*)
    if [ "$(grep -c "ssm send-command" "$FAKE_AWS_LOG")" -le "${FAKE_NOT_READY_FOR:-0}" ]; then
        exit 255
    fi
    echo "$*" > "$FAKE_AWS_LOG.last_command"
    echo "command-1" ;;
*"ssm get-command-invocation"*)
    if grep -q -- "--json" "$FAKE_AWS_LOG.last_command"; then
        [ "$FAKE_MACHINE" = "current" ] || { printf 'Failed\t'; exit 0; }
        printf 'Success\t{"indexed": 3, "run": {"active_seconds": 60}}'
    elif grep -q "describe --name" "$FAKE_AWS_LOG.last_command" && [ "$FAKE_MACHINE" = "old" ]; then
        printf 'Failed\tUsage: bootstrap.sh <install|status|update|uninstall>'
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
    (fake_bin / "python3").write_text(
        "#!/usr/bin/env bash\n"
        f'[ "$1" = "-c" ] && exec {sys.executable} "$@"\n'
        "echo '  (cost estimate)'\n"
    )
    (fake_bin / "python3").chmod(0o755)
    (fake_bin / "sleep").write_text("#!/usr/bin/env bash\n")
    (fake_bin / "sleep").chmod(0o755)
    log = tmp_path / "aws.log"

    def run(
        stack_exists,
        *extra,
        overwrite_while_running=False,
        script="deploy.sh",
        machine="current",
        not_ready_for=0,
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
            "FAKE_NOT_READY_FOR": str(not_ready_for),
        }
        if script != "deploy.sh":
            command = ["bash", str(scripts / script), "demo", *extra]
            result = subprocess.run(command, capture_output=True, text=True, env=env)
            return result, log.read_text().splitlines()
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


DESCRIPTION = {"title": "Demo Museum", "example_queries": ["a quilt"]}


@pytest.fixture()
def description(tmp_path):
    path = tmp_path / "collection.json"
    path.write_text(json.dumps(DESCRIPTION))
    return path


def sent_description(calls):
    command = [c for c in calls if "ssm send-command" in c][-1]
    encoded = command.split("--collection-base64 ")[1].split('"')[0]
    return json.loads(base64.b64decode(encoded))


def test_describe_sends_the_file_to_the_machine(fake_deploy, description):
    result, calls = fake_deploy(True, "--file", str(description), script="describe.sh")
    assert result.returncode == 0, result.stderr
    assert sent_description(calls) == DESCRIPTION
    assert "describe --name demo" in calls[-2]


def test_describe_keeps_trying_while_a_new_machine_starts_up(fake_deploy, description):
    result, calls = fake_deploy(
        True, "--file", str(description), script="describe.sh", not_ready_for=3
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("not ready for it yet") == 3
    assert sent_description(calls) == DESCRIPTION


def test_describe_stops_at_once_when_the_machine_rejects_the_file(
    fake_deploy, description
):
    result, calls = fake_deploy(
        True, "--file", str(description), script="describe.sh", machine="old"
    )
    assert result.returncode != 0
    assert "Usage: bootstrap.sh" in result.stderr
    assert "keeps its previous description" in result.stderr
    assert len([c for c in calls if "ssm send-command" in c]) == 1


def test_describe_refuses_a_file_that_is_not_a_json_object(fake_deploy, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text('{"title": ')
    result, calls = fake_deploy(True, "--file", str(broken), script="describe.sh")
    assert result.returncode != 0
    assert "not a JSON object" in result.stderr
    assert not any("ssm send-command" in c for c in calls)


def test_deploy_delivers_the_description_once_the_machine_exists(
    fake_deploy, description, tmp_path
):
    result, deploys = fake_deploy(False, "--collection-file", str(description))
    assert result.returncode == 0, result.stderr
    assert len(deploys) == 1
    calls = (tmp_path / "aws.log").read_text().splitlines()
    assert sent_description(calls) == DESCRIPTION
    assert "Visitors see the new description" in result.stdout


def test_deploy_creates_nothing_when_the_description_is_broken(fake_deploy, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("[]")
    result, deploys = fake_deploy(False, "--collection-file", str(broken))
    assert result.returncode != 0
    assert deploys == []
    assert "Nothing was changed" in result.stderr


FAKE_DOCKER = """#!/usr/bin/env bash
shift 5
exec {python} "$@"
"""


@pytest.fixture()
def installed_collection(tmp_path):
    import os

    data_root = tmp_path / "dce"
    (data_root / "collections" / "demo").mkdir(parents=True)
    (data_root / "run-demo.sh").write_text('docker run "example/image:1" serve\n')
    fake_bin = tmp_path / "docker-bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text(FAKE_DOCKER.format(python=sys.executable))
    (fake_bin / "docker").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}

    def run(name, *flags):
        command = ["bash", str(ROOT / "deploy/bootstrap.sh"), "describe"]
        command += ["--name", name, "--data-root", str(data_root), *flags]
        return subprocess.run(command, capture_output=True, text=True, env=env)

    return run, data_root / "collections" / "demo" / "collection.json"


def test_bootstrap_describe_replaces_the_description_of_a_running_site(
    installed_collection, description
):
    run, placed = installed_collection
    encoded = base64.b64encode(description.read_bytes()).decode()
    result = run("demo", "--collection-base64", encoded)
    assert result.returncode == 0, result.stderr
    assert json.loads(placed.read_text()) == DESCRIPTION
    assert placed.stat().st_mode & 0o004, "the container user must be able to read it"
    assert [p.name for p in placed.parent.iterdir()] == ["collection.json"]


def test_bootstrap_describe_keeps_the_old_description_when_the_new_one_is_broken(
    installed_collection, description, tmp_path
):
    run, placed = installed_collection
    assert run("demo", "--collection-file", str(description)).returncode == 0
    broken = tmp_path / "broken.json"
    broken.write_text("not json")
    result = run("demo", "--collection-file", str(broken))
    assert result.returncode != 0
    assert "not a JSON object" in result.stderr
    assert json.loads(placed.read_text()) == DESCRIPTION
    assert [p.name for p in placed.parent.iterdir()] == ["collection.json"]


def test_bootstrap_describe_refuses_a_collection_that_is_not_installed(
    installed_collection, description
):
    run, _ = installed_collection
    result = run("other", "--collection-file", str(description))
    assert result.returncode != 0
    assert "no collection named other" in result.stderr
