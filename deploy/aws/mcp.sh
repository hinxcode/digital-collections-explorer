#!/usr/bin/env bash

set -euo pipefail

{

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
SWITCH=""
BOOTSTRAP_URL=""
# Seconds to wait for the site to answer again after it restarts.
RESTART_TIMEOUT=300

fail() { echo "ERROR: $*" >&2; exit 1; }
source "$HERE/machine.sh"

[ $# -ge 1 ] || fail "usage: mcp.sh NAME --on|--off [--region REGION] [--bootstrap-url URL]"
NAME="$1"
shift
while [ $# -gt 0 ]; do
    case "$1" in
    --on) SWITCH="on"; shift ;;
    --off) SWITCH="off"; shift ;;
    --region) REGION="$2"; shift 2 ;;
    --bootstrap-url) BOOTSTRAP_URL="$2"; shift 2 ;;
    *) fail "unknown option: $1" ;;
    esac
done
[ -n "$SWITCH" ] || fail "--on or --off is required"

STACK="dce-$NAME"
stack_value() {
    aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
        --query "$1" --output text 2>/dev/null
}
instance="$(stack_value "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue")" ||
    fail "no deployment named $NAME in $REGION"
[ -n "$instance" ] && [ "$instance" != "None" ] || fail "no deployment named $NAME in $REGION"
site="$(stack_value "Stacks[0].Outputs[?OutputKey=='SiteUrl'].OutputValue")" || site=""
[ -n "$site" ] && [ "$site" != "None" ] || fail "could not read the address of $NAME"
if [ -z "$BOOTSTRAP_URL" ]; then
    BOOTSTRAP_URL="$(stack_value "Stacks[0].Parameters[?ParameterKey=='BootstrapUrl'].ParameterValue")" ||
        BOOTSTRAP_URL=""
fi
[ -n "$BOOTSTRAP_URL" ] && [ "$BOOTSTRAP_URL" != "None" ] ||
    BOOTSTRAP_URL="https://raw.githubusercontent.com/L4CCH/digital-collections-explorer/main/deploy/bootstrap.sh"

if [ "$SWITCH" = "on" ]; then
    echo "Turning MCP on for $NAME (machine $instance), with links to $site"
    command="mcp --name $NAME --on --public-url $site"
else
    echo "Turning MCP off for $NAME (machine $instance)"
    command="mcp --name $NAME --off"
fi
run_on_machine_when_ready \
    "$(bootstrap_commands "$command")" \
    "the machine did not switch MCP. If it runs an older version, run deploy/aws/update.sh first." \
    "deploy/aws/mcp.sh $NAME --$SWITCH --region $REGION"

[ "$SWITCH" = "on" ] || { echo "Done. Once the site has restarted, it no longer answers at /mcp."; exit 0; }

echo "The site is restarting. Waiting for $site/mcp to answer."
SECONDS=0
while :; do
    answer="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$site/mcp" \
        -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{}')" ||
        answer="000"
    case "$answer" in
    2?? | 400 | 405 | 406) break ;;
    404)
        health="$(curl -s -o /dev/null -w '%{http_code}' "$site/api/health")" || health="000"
        [ "$health" = "200" ] &&
            fail "the site is up but does not answer at /mcp, so it runs a version without MCP. Switch it to a newer image with deploy/aws/update.sh $NAME --image IMAGE, then run this again."
        ;;
    esac
    [ "$SECONDS" -lt "$RESTART_TIMEOUT" ] ||
        fail "the site did not answer at $site/mcp within $RESTART_TIMEOUT seconds. See deploy/aws/status.sh $NAME --region $REGION"
    sleep 10
done

echo "Done. AI assistants can connect to $site/mcp, for example:"
echo "  claude mcp add --transport http $NAME $site/mcp"
case "$site" in
http://*) echo "Assistants that connect from the cloud, such as Claude's custom connectors, need https://. Deploy with --https for that." ;;
esac

exit 0
}
