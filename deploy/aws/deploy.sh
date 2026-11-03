#!/usr/bin/env bash
#
#

set -euo pipefail

{

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
SOURCE=""
FROM=""
FETCH_VIA=""
ANONYMOUS=""
SOURCE_BUCKET=""
LIMIT=""
INSTANCE_TYPE=""
DISK_GIB=""
ALLOWED_CIDR=""
BUDGET=""
EMAIL=""
CHANGES=()
IMAGE=""
BOOTSTRAP_URL=""
COLLECTION_FILE=""
HTTPS=""
DOMAIN=""
CERTIFICATE_ARN=""
NO_DOMAIN="false"
BASE_PATH=""
ASSUME_YES="false"

usage() {
    cat <<'EOF'
Usage: deploy.sh NAME (--source SRC | --from S3URI) [options]

Run it again with the same NAME and only the options you want to change.
Everything you leave out keeps the value the deployment already has.

  --source SRC          s3://bucket/prefix or the URL of a .parquet manifest to index
  --from S3URI          or s3://bucket/prefix holding a collection prepared elsewhere, which
                        the machine copies instead of indexing. One of the two is required
                        the first time.
  --fetch-via S3URI     bucket holding the files, when manifest URLs are not downloadable
  --anonymous           read S3 without credentials (public buckets)
  --source-bucket NAME  private bucket in this account that the machine may read
                        (with --from, the bucket it names)
  --limit N             only index the first N images
  --collection-file F   the collection.json that describes the collection to visitors
  --instance-type TYPE  default t3.medium
  --disk-gib N          default 30
  --region REGION       default us-west-2, or AWS_REGION
  --allowed-cidr CIDR   who may open the site (default: everyone)
  --https               open the site to everyone over HTTPS, through CloudFront
  --no-https            go back to plain HTTP on the machine's own address
  --domain NAME         with --https, also serve the site at a domain of your own, such as
                        collection.example.org. Needs --certificate-arn
  --certificate-arn ARN an issued AWS Certificate Manager certificate for that domain, in
                        us-east-1, where CloudFront looks for certificates
  --no-domain           serve the site at its CloudFront address only
  --base-path PATH      serve the site under PATH, such as /explorer, for a website of
                        your own whose proxy forwards that path here. Only when the
                        machine is first created
  --budget USD          email an alert when the monthly bill passes this amount
  --email ADDRESS       where to send that alert
  --image IMAGE         container image to install. Later, switch versions with update.sh
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
    --from) FROM="$2"; shift 2 ;;
    --fetch-via) FETCH_VIA="$2"; shift 2 ;;
    --anonymous) ANONYMOUS="true"; shift ;;
    --source-bucket) SOURCE_BUCKET="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --collection-file) COLLECTION_FILE="$2"; shift 2 ;;
    --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
    --disk-gib) DISK_GIB="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --allowed-cidr) ALLOWED_CIDR="$2"; shift 2 ;;
    --https) HTTPS="true"; shift ;;
    --no-https) HTTPS="false"; shift ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --certificate-arn) CERTIFICATE_ARN="$2"; shift 2 ;;
    --no-domain) NO_DOMAIN="true"; shift ;;
    --base-path) BASE_PATH="$2"; shift 2 ;;
    --budget) BUDGET="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --bootstrap-url) BOOTSTRAP_URL="$2"; shift 2 ;;
    --yes) ASSUME_YES="true"; shift ;;
    -h | --help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
    esac
done

[[ "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "NAME may only contain lowercase letters, digits and hyphens"
if [ -n "$BASE_PATH" ]; then
    BASE_PATH="/${BASE_PATH#/}"
    BASE_PATH="${BASE_PATH%/}"
    [[ "$BASE_PATH" =~ ^(/[A-Za-z0-9._~-]+)+$ ]] ||
        fail "--base-path must look like /explorer: letters, digits, '.', '_', '~' and '-' between slashes"
fi
[ -z "$COLLECTION_FILE" ] || [ -f "$COLLECTION_FILE" ] || fail "file not found: $COLLECTION_FILE"
command -v aws >/dev/null 2>&1 || fail "the AWS CLI is not installed"

current_parameter() {
    echo "$CURRENT_PARAMETERS" | awk -F'\t' -v key="$1" '$1 == key && $2 != "None" { print $2 }'
}

keep() {
    local variable="$1" key="$2" label="$3" current
    current="$(current_parameter "$key")"
    if [ -z "${!variable}" ]; then
        printf -v "$variable" '%s' "$current"
    elif [ "${!variable}" != "$current" ]; then
        CHANGES+=("$label: ${current:-none} -> ${!variable}")
    fi
}

set_at_first_boot() {
    local flag="$1" given="$2" current
    current="$(current_parameter "$3")"
    [ -z "$given" ] || [ "$given" = "$current" ] ||
        fail "$flag only applies when a machine is first created, and this one was created with '$current'. Changing it now would restart the machine and change nothing else. Leave $flag out. To index something else, remove this deployment and create a new one."
}

STACK="dce-$NAME"
LATEST_IMAGE_PARAMETER="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)" ||
    fail "could not sign in to AWS. Check your credentials."

EXISTING_INSTANCE="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text 2>/dev/null)" || EXISTING_INSTANCE=""

if [ -n "$EXISTING_INSTANCE" ] && [ "$EXISTING_INSTANCE" != "None" ]; then
    IS_UPDATE="true"
    MACHINE_IMAGE="$(aws ec2 describe-instances --region "$REGION" --instance-ids "$EXISTING_INSTANCE" \
        --query "Reservations[0].Instances[0].ImageId" --output text)" ||
        fail "could not read the existing machine. Nothing was changed."
    CURRENT_PARAMETERS="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
        --query "Stacks[0].Parameters[].[ParameterKey,ParameterValue]" --output text)" ||
        fail "could not read the existing deployment. Nothing was changed."

    CURRENT_DISK="$(current_parameter DiskSizeGiB)"
    if [ -n "$DISK_GIB" ] && [ "$DISK_GIB" != "$CURRENT_DISK" ]; then
        fail "this deployment has a $CURRENT_DISK GB disk. Changing it to $DISK_GIB GB would replace the machine and delete its index. Leave --disk-gib out."
    fi
    DISK_GIB="$CURRENT_DISK"

    CURRENT_IMAGE="$(current_parameter Image)"
    if [ -n "$IMAGE" ] && [ "$IMAGE" != "$CURRENT_IMAGE" ]; then
        fail "--image only applies when a machine is first created. Changing it here would restart the machine and it would still run the version it runs now. To switch versions, run: deploy/aws/update.sh $NAME --image $IMAGE --region $REGION"
    fi
    IMAGE=""
    set_at_first_boot --source "$SOURCE" Source
    set_at_first_boot --from "$FROM" PreparedFrom
    set_at_first_boot --fetch-via "$FETCH_VIA" FetchVia
    set_at_first_boot --anonymous "$ANONYMOUS" AnonymousS3
    set_at_first_boot --limit "$LIMIT" Limit
    set_at_first_boot --bootstrap-url "$BOOTSTRAP_URL" BootstrapUrl
    set_at_first_boot --base-path "$BASE_PATH" BasePath
    SOURCE="$(current_parameter Source)"
    FROM="$(current_parameter PreparedFrom)"
    FETCH_VIA="$(current_parameter FetchVia)"
    ANONYMOUS="$(current_parameter AnonymousS3)"
    LIMIT="$(current_parameter Limit)"
    MACHINE_BOOTSTRAP_URL="$(current_parameter BootstrapUrl)"
    BASE_PATH="$(current_parameter BasePath)"
    BOOTSTRAP_URL=""

    CURRENT_HTTPS="$(current_parameter PublicHttps)"
    [ -n "$CURRENT_HTTPS" ] || CURRENT_HTTPS="false"
    keep INSTANCE_TYPE InstanceType "Machine type"
    keep SOURCE_BUCKET SourceBucket "Private bucket the machine may read"
    keep BUDGET MonthlyBudgetUsd "Spending alert (USD per month)"
    keep EMAIL BudgetEmail "Spending alert address"
    keep HTTPS PublicHttps "Public HTTPS"
    if [ "$NO_DOMAIN" = "true" ]; then
        CURRENT_DOMAIN="$(current_parameter Domain)"
        [ -z "$CURRENT_DOMAIN" ] || CHANGES+=("Domain of your own: $CURRENT_DOMAIN -> none")
    else
        keep DOMAIN Domain "Domain of your own"
        keep CERTIFICATE_ARN CertificateArn "Certificate for the domain"
    fi
    [ "$HTTPS" = "true" ] || keep ALLOWED_CIDR AllowedCidr "Who may open the site"
else
    IS_UPDATE="false"
    CURRENT_HTTPS="false"
    MACHINE_BOOTSTRAP_URL="$BOOTSTRAP_URL"
    [ -n "$SOURCE" ] || [ -n "$FROM" ] || fail "--source or --from is required"
    [ -z "$SOURCE" ] || [ -z "$FROM" ] || fail "use --source or --from, not both"
    if [ -n "$FROM" ]; then
        [[ "$FROM" =~ ^s3://([a-z0-9][a-z0-9.-]*)(/[A-Za-z0-9._/-]*)?$ ]] ||
            fail "--from must be an s3:// address made of letters, digits, '.', '_', '-' and '/'"
        FROM_BUCKET="${BASH_REMATCH[1]}"
        [ -z "$FETCH_VIA$ANONYMOUS$LIMIT" ] || fail "--fetch-via, --anonymous and --limit only apply to --source"
        [ -n "$SOURCE_BUCKET" ] || SOURCE_BUCKET="$FROM_BUCKET"
        [ "$SOURCE_BUCKET" = "$FROM_BUCKET" ] ||
            fail "the machine may only read the bucket $SOURCE_BUCKET, so it could not copy $FROM"
    else
        case "$SOURCE" in
        s3://* | http://* | https://*) ;;
        *) fail "the cloud machine cannot see files on this computer. --source must be an s3:// or https:// address" ;;
        esac
    fi
    [ -n "$ANONYMOUS" ] || ANONYMOUS="false"
    [ -n "$LIMIT" ] || LIMIT="0"
    [ -n "$INSTANCE_TYPE" ] || INSTANCE_TYPE="t3.medium"
    [ -n "$DISK_GIB" ] || DISK_GIB="30"
    [ -n "$ALLOWED_CIDR" ] || ALLOWED_CIDR="0.0.0.0/0"
    [ -n "$BUDGET" ] || BUDGET="0"
    MACHINE_IMAGE="$(aws ssm get-parameter --region "$REGION" --name "$LATEST_IMAGE_PARAMETER" \
        --query Parameter.Value --output text)" ||
        fail "could not look up the Amazon Linux image for $REGION."
fi
case "$MACHINE_IMAGE" in
ami-*) ;;
*) fail "unexpected machine image id: $MACHINE_IMAGE. Nothing was changed." ;;
esac

[ -n "$HTTPS" ] || HTTPS="false"
if [ "$NO_DOMAIN" = "true" ]; then
    [ -z "$DOMAIN$CERTIFICATE_ARN" ] || fail "use --domain or --no-domain, not both. Nothing was changed."
    DOMAIN=""
    CERTIFICATE_ARN=""
fi
if [ -n "$DOMAIN" ]; then
    [ "$HTTPS" = "true" ] ||
        fail "a domain of your own is served through CloudFront, so it needs --https. To stop serving $DOMAIN, add --no-domain. Nothing was changed."
    [[ "$DOMAIN" =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$ ]] ||
        fail "--domain must be a domain name in lowercase, such as collection.example.org. Nothing was changed."
    [ -n "$CERTIFICATE_ARN" ] ||
        fail "--domain needs --certificate-arn: a certificate for $DOMAIN in AWS Certificate Manager, in us-east-1, where CloudFront looks for certificates. Request one with
  aws acm request-certificate --region us-east-1 --domain-name $DOMAIN --validation-method DNS
add the DNS record that 'aws acm describe-certificate --region us-east-1 --certificate-arn ARN' shows, and run this again once the certificate is issued. Nothing was changed."
    [[ "$CERTIFICATE_ARN" =~ ^arn:aws:acm:us-east-1:[0-9]{12}:certificate/[0-9a-f-]+$ ]] ||
        fail "--certificate-arn must name a certificate in us-east-1, where CloudFront looks for certificates, whatever region the site runs in. Nothing was changed."
    CERTIFICATE="$(aws acm describe-certificate --region us-east-1 --certificate-arn "$CERTIFICATE_ARN" \
        --query "[Certificate.Status, join(' ', Certificate.SubjectAlternativeNames)]" --output text)" ||
        fail "could not read the certificate $CERTIFICATE_ARN. Nothing was changed."
    read -r CERTIFICATE_STATUS CERTIFICATE_NAMES <<<"$CERTIFICATE"
    read -r -a NAMES <<<"$CERTIFICATE_NAMES"
    [ "$CERTIFICATE_STATUS" = "ISSUED" ] ||
        fail "the certificate is $CERTIFICATE_STATUS, not ISSUED. Add the DNS record that 'aws acm describe-certificate --region us-east-1 --certificate-arn $CERTIFICATE_ARN' shows, and run this again once it is issued. Nothing was changed."
    COVERED="false"
    for name in "${NAMES[@]}"; do
        [ "$name" = "$DOMAIN" ] && COVERED="true"
        [ "$name" = "*.${DOMAIN#*.}" ] && COVERED="true"
    done
    [ "$COVERED" = "true" ] ||
        fail "the certificate covers $CERTIFICATE_NAMES, not $DOMAIN. Nothing was changed."
elif [ -n "$CERTIFICATE_ARN" ]; then
    fail "--certificate-arn only applies together with --domain. Nothing was changed."
fi
CLOUDFRONT_PREFIX_LIST=""
if [ "$HTTPS" = "true" ]; then
    [ -z "$ALLOWED_CIDR" ] || [ "$ALLOWED_CIDR" = "0.0.0.0/0" ] ||
        fail "a site served over HTTPS is open to everyone, so --allowed-cidr cannot be used with it. Nothing was changed."
    ALLOWED_CIDR="0.0.0.0/0"
    CLOUDFRONT_PREFIX_LIST="$(aws ec2 describe-managed-prefix-lists --region "$REGION" \
        --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
        --query "PrefixLists[0].PrefixListId" --output text)" || CLOUDFRONT_PREFIX_LIST=""
    case "$CLOUDFRONT_PREFIX_LIST" in
    pl-*) ;;
    *) fail "could not find the CloudFront address list for $REGION. Nothing was changed." ;;
    esac
fi

PYTHON="python3"
[ -x "$HERE/../../venv/bin/python" ] && PYTHON="$HERE/../../venv/bin/python"
if [ -n "$COLLECTION_FILE" ]; then
    "$PYTHON" -c "import json, sys; assert isinstance(json.load(open(sys.argv[1])), dict)" "$COLLECTION_FILE" 2>/dev/null ||
        fail "$COLLECTION_FILE is not a JSON object. See collection.example.json. Nothing was changed."
fi

echo
if [ "$IS_UPDATE" = "true" ]; then
    echo "A deployment named $NAME already exists (machine $EXISTING_INSTANCE)."
    echo "It will be updated in place. The index on its disk and its address are kept."
    echo "If the machine type changes, the site is offline for a few minutes while it restarts."
    echo
    if [ "${#CHANGES[@]}" -gt 0 ]; then
        echo "What changes:"
        printf '  %s\n' "${CHANGES[@]}"
    else
        echo "None of its settings change."
    fi
    echo
    echo "After the update it will consist of, in AWS account ending in ${ACCOUNT: -4}, region $REGION:"
else
    echo "This will create the following in AWS account ending in ${ACCOUNT: -4}, region $REGION:"
fi
echo
if [ -n "$FROM" ]; then
    echo "  1 virtual machine ($INSTANCE_TYPE) that copies the collection prepared in '$FROM' and serves it"
else
    echo "  1 virtual machine ($INSTANCE_TYPE) that indexes '$SOURCE' and then serves the site"
fi
echo "  1 disk of $DISK_GIB GB, deleted together with the machine"
echo "  1 fixed public address"
if [ "$HTTPS" = "true" ]; then
    echo "  1 firewall rule allowing web traffic (port 80) from CloudFront only"
    if [ -n "$DOMAIN" ]; then
        echo "  1 CloudFront distribution that serves the site at https://$DOMAIN and at its own https:// address"
    else
        echo "  1 CloudFront distribution that gives the site a public https:// address"
    fi
else
    echo "  1 firewall rule allowing web traffic (port 80) from $ALLOWED_CIDR"
fi
if [ -n "$SOURCE_BUCKET" ]; then
    echo "  1 permission role so administrators can connect without SSH and the machine can read $SOURCE_BUCKET"
else
    echo "  1 permission role so administrators can connect without SSH"
fi
[ "$BUDGET" != "0" ] && echo "  1 spending alert at \$$BUDGET per month, sent to $EMAIL"
[ -n "$COLLECTION_FILE" ] && echo "  The site will describe itself with $COLLECTION_FILE"
[ -n "$BASE_PATH" ] && echo "  The site answers under $BASE_PATH, for a proxy of your own to forward there"
echo
echo "Estimated cost while it is running:"
"$PYTHON" "$HERE/estimate_cost.py" --region "$REGION" \
    --instance-type "$INSTANCE_TYPE" --disk-gib "$DISK_GIB" || true
if [ "$HTTPS" = "true" ]; then
    echo "  CloudFront: free up to 1 TB and 10 million requests per month, then about \$0.085 per GB"
fi
echo
echo "Remove everything again with: deploy/aws/destroy.sh $NAME --region $REGION"
echo

if [ "$ASSUME_YES" != "true" ]; then
    if [ "$IS_UPDATE" = "true" ]; then
        read -r -p "Update this deployment? Type yes to continue: " answer
    else
        read -r -p "Create these resources? Type yes to continue: " answer
    fi
    [ "$answer" = "yes" ] || { echo "Nothing was changed."; exit 0; }
fi

overrides=(
    "CollectionName=$NAME" "Source=$SOURCE" "PreparedFrom=$FROM" "FetchVia=$FETCH_VIA"
    "AnonymousS3=$ANONYMOUS" "SourceBucket=$SOURCE_BUCKET" "Limit=$LIMIT"
    "InstanceType=$INSTANCE_TYPE" "DiskSizeGiB=$DISK_GIB" "AllowedCidr=$ALLOWED_CIDR"
    "MonthlyBudgetUsd=$BUDGET" "BudgetEmail=$EMAIL" "MachineImageId=$MACHINE_IMAGE"
    "PublicHttps=$HTTPS" "CloudFrontPrefixList=$CLOUDFRONT_PREFIX_LIST"
    "Domain=$DOMAIN" "CertificateArn=$CERTIFICATE_ARN" "BasePath=$BASE_PATH"
)
[ -n "$IMAGE" ] && overrides+=("Image=$IMAGE")
[ -n "$BOOTSTRAP_URL" ] && overrides+=("BootstrapUrl=$BOOTSTRAP_URL")

aws cloudformation deploy \
    --region "$REGION" \
    --stack-name "$STACK" \
    --template-file "$HERE/template.yaml" \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset \
    --tags "dce-collection=$NAME" \
    --parameter-overrides "${overrides[@]}"

echo
aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output text
echo
if [ "$IS_UPDATE" = "true" ]; then
    echo "The deployment was updated. The index and the address were kept."
elif [ -n "$FROM" ]; then
    echo "The machine is now installing and copying $FROM. The site opens when the copy finishes."
else
    echo "The machine is now installing and indexing. The site opens when indexing finishes."
fi
echo "Follow progress with: deploy/aws/status.sh $NAME --region $REGION"

if [ -n "$DOMAIN" ]; then
    TARGET="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
        --query "Stacks[0].Outputs[?OutputKey=='CloudFrontAddress'].OutputValue" --output text)" || TARGET=""
    echo
    echo "Point $DOMAIN at ${TARGET:-the CloudFrontAddress above} with a CNAME record where your domain's DNS is kept"
    echo "(on Route 53, an alias record also works for a root domain). Until then, the site answers at https://${TARGET:-its CloudFront address}."
fi

if [ "$HTTPS" = "true" ] || [ "$CURRENT_HTTPS" = "true" ]; then
    echo
    hops=0
    [ "$HTTPS" = "true" ] && hops=1
    configure_flags=(--set "proxy_hops=$hops" --region "$REGION")
    [ -n "$MACHINE_BOOTSTRAP_URL" ] && configure_flags+=(--bootstrap-url "$MACHINE_BOOTSTRAP_URL")
    "$HERE/configure.sh" "$NAME" "${configure_flags[@]}" ||
        echo "The deployment itself succeeded, but the site cannot tell visitors apart yet. Once the machine runs a current version, run: deploy/aws/configure.sh $NAME --set proxy_hops=$hops --region $REGION"
fi

if [ -n "$COLLECTION_FILE" ]; then
    echo
    describe_flags=(--file "$COLLECTION_FILE" --region "$REGION")
    [ -n "$MACHINE_BOOTSTRAP_URL" ] && describe_flags+=(--bootstrap-url "$MACHINE_BOOTSTRAP_URL")
    "$HERE/describe.sh" "$NAME" "${describe_flags[@]}" ||
        echo "The deployment itself succeeded. Only the description is missing."
fi

exit 0
}
