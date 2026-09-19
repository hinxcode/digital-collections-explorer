#!/usr/bin/env bash
#
# Remove everything deploy.sh created for one collection, including its index.
#
#   deploy/aws/destroy.sh my-collection

set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }

[ $# -ge 1 ] || fail "usage: destroy.sh NAME [--region REGION] [--yes]"
NAME="$1"
shift
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
ASSUME_YES="false"
while [ $# -gt 0 ]; do
    case "$1" in
    --region) REGION="$2"; shift 2 ;;
    --yes) ASSUME_YES="true"; shift ;;
    *) fail "unknown option: $1" ;;
    esac
done
STACK="dce-$NAME"

aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" >/dev/null 2>&1 ||
    fail "no deployment named $NAME in $REGION"

echo "This permanently deletes the following in $REGION:"
aws cloudformation describe-stack-resources --region "$REGION" --stack-name "$STACK" \
    --query "StackResources[].[ResourceType,PhysicalResourceId]" --output text |
    sed 's/^/  /'
echo
echo "The index on the machine's disk is deleted too. It can be rebuilt from the source."

if [ "$ASSUME_YES" != "true" ]; then
    read -r -p "Delete all of this? Type yes to continue: " answer
    [ "$answer" = "yes" ] || { echo "Nothing was deleted."; exit 0; }
fi

aws cloudformation delete-stack --region "$REGION" --stack-name "$STACK"
echo "Deleting. This takes a few minutes..."
aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$STACK"
echo "Everything created for $NAME has been removed. Billing for it has stopped."
