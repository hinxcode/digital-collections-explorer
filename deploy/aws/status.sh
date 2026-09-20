#!/usr/bin/env bash
#
# Show how a deployed collection is doing: the stack, indexing progress, the site.
#
#   deploy/aws/status.sh my-collection

set -euo pipefail

# Bash reads a script from disk while it runs. Without these braces, saving this file
# during one of its long waits makes bash continue from the old position in the new
# text and run whatever it finds there. The braces make it read everything up front.
{

# Seconds to wait for the machine to answer the progress question.
COMMAND_TIMEOUT=60

fail() { echo "ERROR: $*" >&2; exit 1; }

[ $# -ge 1 ] || fail "usage: status.sh NAME [--region REGION]"
NAME="$1"
shift
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
[ "${1:-}" = "--region" ] && REGION="$2"
STACK="dce-$NAME"

output() {
    aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

state="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].StackStatus" --output text 2>/dev/null)" ||
    fail "no deployment named $NAME in $REGION"
instance="$(output InstanceId)"
url="$(output SiteUrl)"

echo "Deployment: $state"
echo "Machine:    $instance"

command_id="$(aws ssm send-command --region "$REGION" --instance-ids "$instance" \
    --document-name AWS-RunShellScript \
    --parameters "commands=['/usr/local/bin/dce-bootstrap status --name $NAME']" \
    --query Command.CommandId --output text 2>/dev/null)" || command_id=""

if [ -n "$command_id" ]; then
    waited=0
    while [ "$waited" -lt "$COMMAND_TIMEOUT" ]; do
        result="$(aws ssm get-command-invocation --region "$REGION" \
            --command-id "$command_id" --instance-id "$instance" \
            --query "[Status,StandardOutputContent]" --output text 2>/dev/null)" || result=""
        case "$result" in
        Success* | Failed*) break ;;
        esac
        sleep 3
        waited=$((waited + 3))
    done
    echo "${result#*$'\t'}"
else
    echo "The machine is not reachable yet. It needs a few minutes after it is created."
fi

if curl -fsS -m 5 "$url/api/health" >/dev/null 2>&1; then
    echo "Site is up: $url"
else
    echo "Site is not up yet: $url"
fi

exit 0
}
