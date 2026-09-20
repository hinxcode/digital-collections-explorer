#!/usr/bin/env bash
#
# Create (or update) one collection's site on AWS. Shows what will be created and
# what it costs, and does nothing until you agree.
#
#   deploy/aws/deploy.sh my-collection --source s3://bucket/prefix --anonymous

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
SOURCE=""
FETCH_VIA=""
ANONYMOUS="false"
SOURCE_BUCKET=""
LIMIT="0"
INSTANCE_TYPE="t3.medium"
DISK_GIB="30"
ALLOWED_CIDR="0.0.0.0/0"
BUDGET="0"
EMAIL=""
IMAGE=""
BOOTSTRAP_URL=""
ASSUME_YES="false"

usage() {
    cat <<'EOF'
Usage: deploy.sh NAME --source SRC [options]

  --source SRC          s3://bucket/prefix or the URL of a .parquet manifest (required)
  --fetch-via S3URI     bucket holding the files, when manifest URLs are not downloadable
  --anonymous           read S3 without credentials (public buckets)
  --source-bucket NAME  private bucket in this account that the machine may read
  --limit N             only index the first N images
  --instance-type TYPE  default t3.medium
  --disk-gib N          default 30
  --region REGION       default us-west-2, or AWS_REGION
  --allowed-cidr CIDR   who may open the site (default: everyone)
  --budget USD          email an alert when the monthly bill passes this amount
  --email ADDRESS       where to send that alert
  --image IMAGE         container image to run
  --bootstrap-url URL   where the machine downloads bootstrap.sh from
  --yes                 do not ask for confirmation
EOF
}

fail() { echo "ERROR: $*" >&2; exit 1; }

[ $# -ge 1 ] || { usage; exit 1; }
case "$1" in -h | --help) usage; exit 0 ;; esac
NAME="$1"
shift
while [ $# -gt 0 ]; do
    case "$1" in
    --source) SOURCE="$2"; shift 2 ;;
    --fetch-via) FETCH_VIA="$2"; shift 2 ;;
    --anonymous) ANONYMOUS="true"; shift ;;
    --source-bucket) SOURCE_BUCKET="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
    --disk-gib) DISK_GIB="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --allowed-cidr) ALLOWED_CIDR="$2"; shift 2 ;;
    --budget) BUDGET="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --bootstrap-url) BOOTSTRAP_URL="$2"; shift 2 ;;
    --yes) ASSUME_YES="true"; shift ;;
    -h | --help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
    esac
done

[ -n "$SOURCE" ] || fail "--source is required"
[[ "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "NAME may only contain lowercase letters, digits and hyphens"
command -v aws >/dev/null 2>&1 || fail "the AWS CLI is not installed"
case "$SOURCE" in
s3://* | http://* | https://*) ;;
*) fail "the cloud machine cannot see files on this computer. --source must be an s3:// or https:// address" ;;
esac

STACK="dce-$NAME"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)" ||
    fail "could not sign in to AWS. Check your credentials."

PYTHON="python3"
[ -x "$HERE/../../venv/bin/python" ] && PYTHON="$HERE/../../venv/bin/python"

echo
# Only the last four digits are shown, so that pasted output does not reveal the
# full account id.
echo "This will create the following in AWS account ending in ${ACCOUNT: -4}, region $REGION:"
echo
echo "  1 virtual machine ($INSTANCE_TYPE) that indexes '$SOURCE' and then serves the site"
echo "  1 disk of $DISK_GIB GB, deleted together with the machine"
echo "  1 fixed public address"
echo "  1 firewall rule allowing web traffic (port 80) from $ALLOWED_CIDR"
echo "  1 permission role so administrators can connect without SSH"
[ "$BUDGET" != "0" ] && echo "  1 spending alert at \$$BUDGET per month, sent to $EMAIL"
echo
echo "Estimated cost while it is running:"
"$PYTHON" "$HERE/estimate_cost.py" --region "$REGION" \
    --instance-type "$INSTANCE_TYPE" --disk-gib "$DISK_GIB" || true
echo
echo "Remove everything again with: deploy/aws/destroy.sh $NAME --region $REGION"
echo

if [ "$ASSUME_YES" != "true" ]; then
    read -r -p "Create these resources? Type yes to continue: " answer
    [ "$answer" = "yes" ] || { echo "Nothing was created."; exit 0; }
fi

overrides=(
    "CollectionName=$NAME" "Source=$SOURCE" "FetchVia=$FETCH_VIA"
    "AnonymousS3=$ANONYMOUS" "SourceBucket=$SOURCE_BUCKET" "Limit=$LIMIT"
    "InstanceType=$INSTANCE_TYPE" "DiskSizeGiB=$DISK_GIB" "AllowedCidr=$ALLOWED_CIDR"
    "MonthlyBudgetUsd=$BUDGET" "BudgetEmail=$EMAIL"
)
[ -n "$IMAGE" ] && overrides+=("Image=$IMAGE")
[ -n "$BOOTSTRAP_URL" ] && overrides+=("BootstrapUrl=$BOOTSTRAP_URL")

aws cloudformation deploy \
    --region "$REGION" \
    --stack-name "$STACK" \
    --template-file "$HERE/template.yaml" \
    --capabilities CAPABILITY_IAM \
    --tags "dce-collection=$NAME" \
    --parameter-overrides "${overrides[@]}"

echo
aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output text
echo
echo "The machine is now installing and indexing. The site opens when indexing finishes."
echo "Follow progress with: deploy/aws/status.sh $NAME --region $REGION"
