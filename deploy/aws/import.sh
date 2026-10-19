#!/usr/bin/env bash

set -euo pipefail

{

# Seconds to wait for the machine to copy the collection, download the image and restart.
COMMAND_TIMEOUT=3600

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
FROM=""
IMAGE=""
BOOTSTRAP_URL="https://raw.githubusercontent.com/hinxcode/digital-collections-explorer/main/deploy/bootstrap.sh"

fail() { echo "ERROR: $*" >&2; exit 1; }

usage="usage: import.sh NAME --from s3://bucket/prefix [--image IMAGE] [--region REGION] [--bootstrap-url URL]"
[ $# -ge 1 ] || fail "$usage"
NAME="$1"
shift
while [ $# -gt 0 ]; do
    case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --bootstrap-url) BOOTSTRAP_URL="$2"; shift 2 ;;
    *) fail "unknown option: $1" ;;
    esac
done
[ -n "$FROM" ] || fail "--from is required. $usage"
[[ "$FROM" =~ ^s3://[a-z0-9][a-z0-9.-]*(/[A-Za-z0-9._/-]*)?$ ]] ||
    fail "--from must be an s3:// address made of letters, digits, '.', '_', '-' and '/'"
[ -z "$IMAGE" ] || [[ "$IMAGE" =~ ^[A-Za-z0-9._/:@-]+$ ]] || fail "--image is not a container image name"
STACK="dce-$NAME"

instance="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text 2>/dev/null)" ||
    fail "no deployment named $NAME in $REGION"

flags="--name $NAME --from $FROM"
[ -n "$IMAGE" ] && flags="$flags --image $IMAGE"

echo "Copying $FROM into $NAME (machine $instance)."
echo "The site keeps its current data until the copy is complete, then restarts on the new one."
echo "The machine must be allowed to read the bucket: deploy/aws/deploy.sh $NAME --source-bucket BUCKET"

command_id="$(aws ssm send-command --region "$REGION" --instance-ids "$instance" \
    --document-name AWS-RunShellScript \
    --parameters "{\"commands\":[\"curl -fsSL $BOOTSTRAP_URL -o /usr/local/bin/dce-bootstrap\",\"chmod +x /usr/local/bin/dce-bootstrap\",\"/usr/local/bin/dce-bootstrap import $flags\"],\"executionTimeout\":[\"$COMMAND_TIMEOUT\"]}" \
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
    sleep 10
    waited=$((waited + 10))
done

echo "${result#*$'\t'}"
case "$result" in
Success*) echo "Done. Check it with: deploy/aws/status.sh $NAME --region $REGION" ;;
*) fail "the import did not finish. The site keeps running on its previous data." ;;
esac

exit 0
}
