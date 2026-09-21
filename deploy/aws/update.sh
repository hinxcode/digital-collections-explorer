#!/usr/bin/env bash

set -euo pipefail

{

# Seconds to wait for the machine to download the image and restart the site.
COMMAND_TIMEOUT=900

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
IMAGE=""
BOOTSTRAP_URL="https://raw.githubusercontent.com/hinxcode/digital-collections-explorer/main/deploy/bootstrap.sh"

fail() { echo "ERROR: $*" >&2; exit 1; }

[ $# -ge 1 ] || fail "usage: update.sh NAME --image IMAGE [--region REGION] [--bootstrap-url URL]"
NAME="$1"
shift
while [ $# -gt 0 ]; do
    case "$1" in
    --image) IMAGE="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --bootstrap-url) BOOTSTRAP_URL="$2"; shift 2 ;;
    *) fail "unknown option: $1" ;;
    esac
done
[ -n "$IMAGE" ] || fail "--image is required"
STACK="dce-$NAME"

instance="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text 2>/dev/null)" ||
    fail "no deployment named $NAME in $REGION"

echo "Switching $NAME (machine $instance) to $IMAGE."
echo "The index and the address are kept. The site is offline for a minute or two."

command_id="$(aws ssm send-command --region "$REGION" --instance-ids "$instance" \
    --document-name AWS-RunShellScript \
    --parameters "commands=['curl -fsSL $BOOTSTRAP_URL -o /usr/local/bin/dce-bootstrap','chmod +x /usr/local/bin/dce-bootstrap','/usr/local/bin/dce-bootstrap update --name $NAME --image $IMAGE']" \
    --query Command.CommandId --output text)" || fail "the machine could not be reached"

waited=0
result=""
while [ "$waited" -lt "$COMMAND_TIMEOUT" ]; do
    result="$(aws ssm get-command-invocation --region "$REGION" \
        --command-id "$command_id" --instance-id "$instance" \
        --query "[Status,StandardOutputContent,StandardErrorContent]" --output text 2>/dev/null)" || result=""
    case "$result" in
    Success* | Failed* | TimedOut* | Cancelled*) break ;;
    esac
    sleep 5
    waited=$((waited + 5))
done

echo "${result#*$'\t'}"
case "$result" in
Success*) echo "Done. Check it with: deploy/aws/status.sh $NAME --region $REGION" ;;
*) fail "the update did not finish. The site keeps running on its previous image." ;;
esac

exit 0
}
