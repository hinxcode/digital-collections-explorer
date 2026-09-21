#!/usr/bin/env bash

# Seconds to keep trying while a new machine starts up.
READY_TIMEOUT=900
# Seconds between attempts.
RETRY_EVERY=15
# Seconds to wait for one attempt to report back.
COMMAND_TIMEOUT=60

bootstrap_commands() {
    local command="$1"
    echo "{\"commands\":[\"curl -fsSL $BOOTSTRAP_URL -o /usr/local/bin/dce-bootstrap\",\"chmod +x /usr/local/bin/dce-bootstrap\",\"/usr/local/bin/dce-bootstrap $command\"]}"
}

attempt_on_machine() {
    local parameters="$1" refusal="$2" command_id result waited=0
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
            fail "$refusal"
            ;;
        esac
        sleep 3
        waited=$((waited + 3))
    done
    return 1
}

run_on_machine_when_ready() {
    local parameters="$1" refusal="$2" retry_hint="$3"
    SECONDS=0
    until attempt_on_machine "$parameters" "$refusal"; do
        if [ "$SECONDS" -ge "$READY_TIMEOUT" ]; then
            fail "the machine did not answer. Try again with: $retry_hint"
        fi
        echo "The machine is not ready for it yet. Trying again in $RETRY_EVERY seconds."
        sleep "$RETRY_EVERY"
    done
}
