#!/usr/bin/env bash

set -euo pipefail

{

# Seconds to keep trying while a new machine starts up.
READY_TIMEOUT=900
# Seconds between attempts.
RETRY_EVERY=15
# Seconds to wait for one attempt to report back.
COMMAND_TIMEOUT=60
# Largest file, in bytes, that fits in one Session Manager command.
MAX_FILE_BYTES=32768

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
FILE=""
BOOTSTRAP_URL="https://raw.githubusercontent.com/hinxcode/digital-collections-explorer/main/deploy/bootstrap.sh"

fail() { echo "ERROR: $*" >&2; exit 1; }

[ $# -ge 1 ] || fail "usage: describe.sh NAME --file collection.json [--region REGION] [--bootstrap-url URL]"
NAME="$1"
shift
while [ $# -gt 0 ]; do
    case "$1" in
    --file) FILE="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --bootstrap-url) BOOTSTRAP_URL="$2"; shift 2 ;;
    *) fail "unknown option: $1" ;;
    esac
done
[ -n "$FILE" ] || fail "--file is required"
[ -f "$FILE" ] || fail "file not found: $FILE"
[ "$(wc -c <"$FILE")" -le "$MAX_FILE_BYTES" ] || fail "$FILE is larger than $MAX_FILE_BYTES bytes"

PYTHON="python3"
[ -x "$HERE/../../venv/bin/python" ] && PYTHON="$HERE/../../venv/bin/python"
"$PYTHON" -c "import json, sys; assert isinstance(json.load(open(sys.argv[1])), dict)" "$FILE" 2>/dev/null ||
    fail "$FILE is not a JSON object. See collection.example.json."

STACK="dce-$NAME"
instance="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text 2>/dev/null)" ||
    fail "no deployment named $NAME in $REGION"

encoded="$(base64 <"$FILE" | tr -d '\n')"
parameters="{\"commands\":[\"curl -fsSL $BOOTSTRAP_URL -o /usr/local/bin/dce-bootstrap\",\"chmod +x /usr/local/bin/dce-bootstrap\",\"/usr/local/bin/dce-bootstrap describe --name $NAME --collection-base64 $encoded\"]}"

attempt() {
    local command_id waited=0
    command_id="$(aws ssm send-command --region "$REGION" --instance-ids "$instance" \
        --document-name AWS-RunShellScript --parameters "$parameters" \
        --query Command.CommandId --output text 2>/dev/null)" || return 1
    while [ "$waited" -lt "$COMMAND_TIMEOUT" ]; do
        result="$(aws ssm get-command-invocation --region "$REGION" \
            --command-id "$command_id" --instance-id "$instance" \
            --query "[Status,StandardOutputContent,StandardErrorContent]" --output text 2>/dev/null)" || result=""
        case "$result" in
        Success*) return 0 ;;
        *"no collection named"*) return 1 ;;
        Failed* | TimedOut* | Cancelled*)
            echo "${result#*$'\t'}" >&2
            fail "the machine could not apply the file. The site keeps its previous description."
            ;;
        esac
        sleep 3
        waited=$((waited + 3))
    done
    return 1
}

echo "Sending $FILE to $NAME (machine $instance)."
result=""
SECONDS=0
until attempt; do
    if [ "$SECONDS" -ge "$READY_TIMEOUT" ]; then
        fail "the machine did not take the file. Try again with: deploy/aws/describe.sh $NAME --file $FILE --region $REGION"
    fi
    echo "The machine is not ready for it yet. Trying again in $RETRY_EVERY seconds."
    sleep "$RETRY_EVERY"
done

echo "Done. Visitors see the new description the next time they load the site."

exit 0
}
