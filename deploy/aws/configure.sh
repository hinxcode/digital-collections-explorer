#!/usr/bin/env bash

set -euo pipefail

{

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
SETTINGS=""
BOOTSTRAP_URL="https://raw.githubusercontent.com/hinxcode/digital-collections-explorer/main/deploy/bootstrap.sh"

fail() { echo "ERROR: $*" >&2; exit 1; }
source "$HERE/machine.sh"

[ $# -ge 1 ] || fail "usage: configure.sh NAME --set KEY=VALUE [--set KEY=VALUE] [--region REGION] [--bootstrap-url URL]"
NAME="$1"
shift
while [ $# -gt 0 ]; do
    case "$1" in
    --set)
        [[ "$2" =~ ^[a-z_]+=[0-9]+$ ]] || fail "--set takes KEY=NUMBER, for example max_upload_mb=20"
        SETTINGS="$SETTINGS --set $2"
        shift 2
        ;;
    --region) REGION="$2"; shift 2 ;;
    --bootstrap-url) BOOTSTRAP_URL="$2"; shift 2 ;;
    *) fail "unknown option: $1" ;;
    esac
done
[ -n "$SETTINGS" ] || fail "--set KEY=VALUE is required"

STACK="dce-$NAME"
instance="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text 2>/dev/null)" ||
    fail "no deployment named $NAME in $REGION"

echo "Changing the limits of $NAME (machine $instance):$SETTINGS"
run_on_machine_when_ready \
    "$(bootstrap_commands "configure --name $NAME$SETTINGS")" \
    "the machine did not change its limits. If it runs an older version, run deploy/aws/update.sh first." \
    "deploy/aws/configure.sh $NAME$SETTINGS --region $REGION"

echo "Done. The site uses the new limits from now on, without a restart."

exit 0
}
