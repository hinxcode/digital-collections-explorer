#!/usr/bin/env bash

set -euo pipefail

{

# Largest file, in bytes, that fits in one Session Manager command.
MAX_FILE_BYTES=32768

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
FILE=""
BOOTSTRAP_URL="https://raw.githubusercontent.com/hinxcode/digital-collections-explorer/main/deploy/bootstrap.sh"

fail() { echo "ERROR: $*" >&2; exit 1; }
source "$HERE/machine.sh"

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

echo "Sending $FILE to $NAME (machine $instance)."
run_on_machine_when_ready \
    "$(bootstrap_commands "describe --name $NAME --collection-base64 $encoded")" \
    "the machine could not apply the file. The site keeps its previous description." \
    "deploy/aws/describe.sh $NAME --file $FILE --region $REGION"

echo "Done. Visitors see the new description the next time they load the site."

exit 0
}
