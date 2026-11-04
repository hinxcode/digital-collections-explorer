#!/usr/bin/env bash

set -euo pipefail

{

# Seconds to wait for the machine to answer.
COMMAND_TIMEOUT=60

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
INDEXED_ON=""

fail() { echo "ERROR: $*" >&2; exit 1; }

[ $# -ge 1 ] || fail "usage: status.sh NAME [--region REGION] [--indexed-on MACHINE_TYPE]"
NAME="$1"
shift
while [ $# -gt 0 ]; do
    case "$1" in
    --region) REGION="$2"; shift 2 ;;
    --indexed-on) INDEXED_ON="$2"; shift 2 ;;
    *) fail "unknown option: $1" ;;
    esac
done
STACK="dce-$NAME"

output() {
    aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

on_machine() {
    local command_id result waited=0
    command_id="$(aws ssm send-command --region "$REGION" --instance-ids "$instance" \
        --document-name AWS-RunShellScript --parameters "commands=['$1']" \
        --query Command.CommandId --output text 2>/dev/null)" || return 1
    while [ "$waited" -lt "$COMMAND_TIMEOUT" ]; do
        result="$(aws ssm get-command-invocation --region "$REGION" \
            --command-id "$command_id" --instance-id "$instance" \
            --query "[Status,StandardOutputContent]" --output text 2>/dev/null)" || result=""
        case "$result" in
        Success*) echo "${result#*$'\t'}"; return 0 ;;
        Failed*) return 1 ;;
        esac
        sleep 3
        waited=$((waited + 3))
    done
    return 1
}

state="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].StackStatus" --output text 2>/dev/null)" ||
    fail "no deployment named $NAME in $REGION"
instance="$(output InstanceId)"
url="$(output SiteUrl)"
machine_type="$(aws ec2 describe-instances --region "$REGION" --instance-ids "$instance" \
    --query "Reservations[0].Instances[0].InstanceType" --output text 2>/dev/null)" || machine_type=""

echo "Deployment: $state"
echo "Machine:    $instance ($machine_type)"
echo

if on_machine "/usr/local/bin/dce-bootstrap status --name $NAME"; then
    report="$(on_machine "/usr/local/bin/dce-bootstrap status --name $NAME --json")" || report=""
    case "$report" in
    "{"*)
        PYTHON="python3"
        [ -x "$HERE/../../venv/bin/python" ] && PYTHON="$HERE/../../venv/bin/python"
        echo
        cost_flags=(--region "$REGION" --current-type "$machine_type")
        [ -n "$INDEXED_ON" ] && cost_flags+=(--indexed-on "$INDEXED_ON")
        echo "$report" | "$PYTHON" "$HERE/run_cost.py" "${cost_flags[@]}" ||
            echo "Costs could not be worked out."
        ;;
    *)
        echo
        echo "This machine runs an older version that cannot report times and costs."
        echo "Update it with: deploy/aws/update.sh $NAME --image IMAGE --region $REGION"
        ;;
    esac
else
    echo "The machine is not reachable yet. It needs a few minutes after it is created."
fi

echo
if curl -fsS -m 5 "$url/api/health" >/dev/null 2>&1; then
    echo "Site is up: $url"
else
    echo "Site is not up yet: $url"
fi

exit 0
}
