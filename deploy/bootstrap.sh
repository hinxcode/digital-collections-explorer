#!/usr/bin/env bash
#
#

set -euo pipefail

{

IMAGE="ghcr.io/hinxcode/digital-collections-explorer:latest"
IMAGE_TAR=""
DATA_ROOT="/opt/dce"
NAME=""
SOURCE=""
FROM=""
FETCH_VIA=""
ANONYMOUS="false"
LIMIT=""
PORT="8000"
BASE_PATH=""
KEEP_DATA="false"
AS_JSON="false"
COLLECTION_FILE=""
COLLECTION_BASE64=""
SETTINGS=()
IMAGE_WAS_GIVEN="false"

# The container runs as this user id, so the data folder must belong to it.
CONTAINER_UID=1000

usage() {
    cat <<'EOF'
Usage: bootstrap.sh <install|status|describe|configure|update|import|uninstall> --name NAME [options]

install options:
  --source SRC        a folder, s3://bucket/prefix, or a .parquet manifest (required)
  --fetch-via S3URI   where the files live when manifest URLs are not downloadable
  --anonymous         read S3 without credentials (public buckets)
  --limit N           only index the first N images
  --port PORT         port for the site (default 8000)
  --base-path PATH    serve the site under this path, e.g. /maps, behind a proxy
  --image IMAGE       container image to run
  --image-tar FILE    load the image from a file instead of downloading it
  --data-root DIR     where collections are stored (default /opt/dce)
  --collection-file FILE  the collection.json that describes the collection to visitors

status options:
  --json              print the full report as JSON

describe options:
  --collection-file FILE  replace the collection.json of a running site. No restart needed.

configure options:
  --set KEY=VALUE     change a limit of a running site. No restart needed. Repeatable.
                      max_upload_mb, searches_per_minute, concurrent_searches, proxy_hops

update options:
  --image IMAGE       switch the site to this image. The index is kept.

import options:
  --from SRC          a collection prepared elsewhere: a folder, or s3://bucket/prefix
                      holding one. It replaces the site's data; the old data is kept.
  --image IMAGE       also switch the site to this image

uninstall options:
  --keep-data         stop the site but keep the index and images
EOF
}

say() { echo "==> $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

parse_args() {
    [ $# -ge 1 ] || { usage; exit 1; }
    ACTION="$1"
    shift
    while [ $# -gt 0 ]; do
        case "$1" in
        --name) NAME="$2"; shift 2 ;;
        --source) SOURCE="$2"; shift 2 ;;
        --from) FROM="$2"; shift 2 ;;
        --fetch-via) FETCH_VIA="$2"; shift 2 ;;
        --anonymous) ANONYMOUS="true"; shift ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --base-path) BASE_PATH="$2"; shift 2 ;;
        --image) IMAGE="$2"; IMAGE_WAS_GIVEN="true"; shift 2 ;;
        --image-tar) IMAGE_TAR="$2"; shift 2 ;;
        --data-root) DATA_ROOT="$2"; shift 2 ;;
        --keep-data) KEEP_DATA="true"; shift ;;
        --json) AS_JSON="true"; shift ;;
        --collection-file) COLLECTION_FILE="$2"; shift 2 ;;
        --collection-base64) COLLECTION_BASE64="$2"; shift 2 ;;
        --set) SETTINGS+=("$2"); shift 2 ;;
        -h | --help) usage; exit 0 ;;
        *) fail "unknown option: $1" ;;
        esac
    done
    [ -n "$NAME" ] || fail "--name is required"
    [[ "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]] ||
        fail "--name may only contain lowercase letters, digits and hyphens"
    COLLECTION_DIR="$DATA_ROOT/collections/$NAME"
    RUNNER="$DATA_ROOT/run-$NAME.sh"
    SERVICE="dce-$NAME"
}

has_systemd() { [ -d /run/systemd/system ]; }

install_docker() {
    if command -v docker >/dev/null 2>&1; then
        say "Docker is already installed"
        return
    fi
    say "Installing Docker"
    if command -v dnf >/dev/null 2>&1 && grep -qi "amazon linux" /etc/os-release; then
        dnf install -y docker
    else
        curl -fsSL https://get.docker.com | sh
    fi
    if has_systemd; then
        systemctl enable --now docker
    fi
}

fetch_image() {
    if [ -n "$IMAGE_TAR" ]; then
        say "Loading the image from $IMAGE_TAR"
        docker load -i "$IMAGE_TAR"
    else
        say "Downloading $IMAGE"
        docker pull "$IMAGE"
    fi
}

resolve_source() {
    SOURCE_MOUNT=""
    case "$SOURCE" in
    s3://* | http://* | https://*)
        SOURCE_ARG="$SOURCE"
        ;;
    *)
        [ -e "$SOURCE" ] || fail "source not found: $SOURCE"
        if [ -d "$SOURCE" ]; then
            SOURCE_MOUNT="-v $(realpath "$SOURCE"):/source:ro"
            SOURCE_ARG="/source"
        else
            SOURCE_MOUNT="-v $(dirname "$(realpath "$SOURCE")"):/source:ro"
            SOURCE_ARG="/source/$(basename "$SOURCE")"
        fi
        ;;
    esac
}

write_runner() {
    local ingest_flags=""
    [ -n "$FETCH_VIA" ] && ingest_flags="$ingest_flags --fetch-via $FETCH_VIA"
    [ "$ANONYMOUS" = "true" ] && ingest_flags="$ingest_flags --anonymous"
    [ -n "$LIMIT" ] && ingest_flags="$ingest_flags --limit $LIMIT"

    cat >"$RUNNER" <<EOF
#!/usr/bin/env bash
set -euo pipefail

if [ ! -f "$COLLECTION_DIR/ingest_complete" ]; then
    docker rm -f $SERVICE-ingest >/dev/null 2>&1 || true
    docker run --rm --name $SERVICE-ingest \\
        -v "$COLLECTION_DIR:/data" $SOURCE_MOUNT \\
        "$IMAGE" ingest $SOURCE_ARG$ingest_flags --json /data/ingest_summary.json
    touch "$COLLECTION_DIR/ingest_complete"
fi

docker rm -f $SERVICE >/dev/null 2>&1 || true
exec docker run --rm --name $SERVICE \\
    -p $PORT:8000 -e DCE_COLLECTION=$NAME -e DCE_BASE_PATH=$BASE_PATH \\
    -v "$COLLECTION_DIR:/data" \\
    "$IMAGE" serve
EOF
    chmod +x "$RUNNER"
}

start_service() {
    if has_systemd; then
        cat >"/etc/systemd/system/$SERVICE.service" <<EOF
[Unit]
Description=Digital Collections Explorer ($NAME)
After=docker.service network-online.target
Requires=docker.service

[Service]
ExecStart=$RUNNER
ExecStop=/usr/bin/docker stop $SERVICE $SERVICE-ingest
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable --now "$SERVICE"
        say "Started as the system service $SERVICE. It restarts after a reboot."
    else
        nohup "$RUNNER" >"$COLLECTION_DIR/runner.log" 2>&1 &
        say "This machine has no systemd, so the site runs in the background"
        say "and will not restart after a reboot. Log: $COLLECTION_DIR/runner.log"
    fi
}

place_description() {
    local image="$1" incoming="$COLLECTION_DIR/.collection.json.incoming"
    if [ -n "$COLLECTION_BASE64" ]; then
        echo "$COLLECTION_BASE64" | base64 -d >"$incoming" ||
            { rm -f "$incoming"; fail "the collection description did not arrive intact"; }
    else
        cp "$COLLECTION_FILE" "$incoming"
    fi
    if ! docker run --rm -i "$image" python -c \
        "import json, sys; assert isinstance(json.load(sys.stdin), dict)" <"$incoming" >/dev/null 2>&1; then
        rm -f "$incoming"
        fail "the collection description is not a JSON object. See collection.example.json."
    fi
    chmod 644 "$incoming"
    mv "$incoming" "$COLLECTION_DIR/collection.json"
    say "Visitors now see the description in $COLLECTION_DIR/collection.json"
}

do_install() {
    [ -n "$SOURCE" ] || fail "--source is required"
    [ -z "$COLLECTION_FILE" ] || [ -f "$COLLECTION_FILE" ] || fail "file not found: $COLLECTION_FILE"
    [ "$(id -u)" -eq 0 ] || fail "run this with sudo"
    install_docker
    fetch_image
    resolve_source
    mkdir -p "$COLLECTION_DIR"
    [ -z "$COLLECTION_FILE" ] || place_description "$IMAGE"
    chown -R "$CONTAINER_UID:$CONTAINER_UID" "$COLLECTION_DIR"
    write_runner
    start_service
    echo
    say "Indexing has started. The site opens on port $PORT when it finishes."
    say "Check progress with: $0 status --name $NAME"
}

do_status() {
    if [ ! -d "$COLLECTION_DIR" ]; then
        fail "no collection named $NAME in $DATA_ROOT"
    fi
    if [ "$AS_JSON" = "true" ]; then
        docker run --rm -v "$COLLECTION_DIR:/data" "$(image_in_use)" ingest --status 2>/dev/null
        return
    fi
    if ! docker run --rm -v "$COLLECTION_DIR:/data" "$(image_in_use)" ingest --report 2>/dev/null; then
        if [ -f "$COLLECTION_DIR/ingest_complete" ]; then
            echo "Indexing: finished"
        else
            echo "Indexing: in progress"
        fi
        docker run --rm -v "$COLLECTION_DIR:/data" "$(image_in_use)" ingest --status 2>/dev/null |
            grep -E '^  "(indexed|pending|skipped|failed)"' | tr -d '",' || true
    fi
    echo "Image: $(image_in_use)"
    if docker ps --format '{{.Names}}' | grep -qx "$SERVICE"; then
        echo "Site: running on port $(port_in_use)"
    else
        echo "Site: not running yet"
    fi
}

do_describe() {
    [ -n "$COLLECTION_FILE" ] || [ -n "$COLLECTION_BASE64" ] || fail "--collection-file is required"
    [ -z "$COLLECTION_FILE" ] || [ -f "$COLLECTION_FILE" ] || fail "file not found: $COLLECTION_FILE"
    [ -f "$RUNNER" ] || fail "no collection named $NAME in $DATA_ROOT"
    [ -w "$COLLECTION_DIR" ] || fail "run this with sudo"
    place_description "$(image_in_use)"
}

do_configure() {
    [ "${#SETTINGS[@]}" -gt 0 ] || fail "--set KEY=VALUE is required"
    [ -f "$RUNNER" ] || fail "no collection named $NAME in $DATA_ROOT"
    [ -w "$COLLECTION_DIR" ] || fail "run this with sudo"
    docker run --rm -v "$COLLECTION_DIR:/data" "$(image_in_use)" \
        python -m src.backend.core.site_settings "${SETTINGS[@]}" ||
        fail "the settings were not changed. If this site runs an older version, update it first."
    say "The site uses these limits from now on"
}

image_in_use() { grep -oE '"[^"]+" (ingest|serve)' "$RUNNER" | head -1 | cut -d'"' -f2; }
port_in_use() { grep -oE '\-p [0-9]+:8000' "$RUNNER" | grep -oE '[0-9]+' | head -1; }

switch_image() {
    local current
    current="$(image_in_use)"
    fetch_image
    sed -i.previous "s|\"$current\"|\"$IMAGE\"|g" "$RUNNER"
    rm -f "$RUNNER.previous"
    PREVIOUS_IMAGE="$current"
}

restart_site() {
    if has_systemd; then
        systemctl restart "$SERVICE"
    else
        docker rm -f "$SERVICE" >/dev/null 2>&1 || true
        nohup "$RUNNER" >"$COLLECTION_DIR/runner.log" 2>&1 &
    fi
}

do_update() {
    [ "$(id -u)" -eq 0 ] || fail "run this with sudo"
    [ -f "$RUNNER" ] || fail "no collection named $NAME in $DATA_ROOT"
    [ "$IMAGE_WAS_GIVEN" = "true" ] || fail "--image is required"
    switch_image
    restart_site
    say "Switched $NAME from $PREVIOUS_IMAGE to $IMAGE. The index was kept."
}

machine_region() {
    local token
    token="$(curl -fsS -m 2 -X PUT http://169.254.169.254/latest/api/token \
        -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null)" || return 0
    curl -fsS -m 2 -H "X-aws-ec2-metadata-token: $token" \
        http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || true
}

copy_prepared() {
    local incoming="$1"
    case "$FROM" in
    s3://*)
        command -v aws >/dev/null 2>&1 || fail "the AWS CLI is needed to copy from $FROM"
        export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-$(machine_region)}"
        local needed available
        needed="$(aws s3 ls "${FROM%/}/" --recursive --summarize | awk '/Total Size/ {print $3}')" ||
            fail "this machine cannot read $FROM. Allow it with deploy.sh --source-bucket"
        available="$(df -P -k "$DATA_ROOT" | awk 'NR == 2 {print $4 * 1024}')"
        [ "${needed:-0}" -lt "${available:-0}" ] ||
            fail "$FROM needs $needed bytes but only $available are free in $DATA_ROOT"
        say "Copying $FROM ($needed bytes)"
        aws s3 sync "${FROM%/}/" "$incoming" --only-show-errors
        ;;
    *)
        [ -d "$FROM" ] || fail "folder not found: $FROM"
        say "Copying $FROM"
        cp -a "$FROM/." "$incoming/"
        ;;
    esac
}

do_import() {
    [ -n "$FROM" ] || fail "--from is required"
    [ -f "$RUNNER" ] || fail "no collection named $NAME in $DATA_ROOT"
    [ -w "$DATA_ROOT/collections" ] || fail "run this with sudo"
    local incoming="$DATA_ROOT/collections/.$NAME.incoming"
    local previous
    previous="$DATA_ROOT/collections/.$NAME.previous-$(date +%Y%m%d%H%M%S)"
    rm -rf "$incoming"
    mkdir -p "$incoming"
    copy_prepared "$incoming" || { rm -rf "$incoming"; fail "could not copy $FROM"; }
    if [ ! -f "$incoming/embeddings/index_info.json" ] ||
        [ ! -f "$incoming/embeddings/metadata.sqlite" ]; then
        rm -rf "$incoming"
        fail "$FROM is not a prepared collection: it needs embeddings/index_info.json and embeddings/metadata.sqlite"
    fi
    if [ -f "$COLLECTION_DIR/settings.json" ]; then
        cp "$COLLECTION_DIR/settings.json" "$incoming/settings.json"
    fi
    touch "$incoming/ingest_complete"
    if [ "$(id -u)" -eq 0 ]; then
        chown -R "$CONTAINER_UID:$CONTAINER_UID" "$incoming"
    fi
    [ "$IMAGE_WAS_GIVEN" = "true" ] && switch_image
    mv "$COLLECTION_DIR" "$previous"
    mv "$incoming" "$COLLECTION_DIR"
    restart_site
    say "$NAME now serves the collection from $FROM, with the same limits as before."
    say "The previous data is kept in $previous. Delete it once the site works."
}

do_uninstall() {
    [ "$(id -u)" -eq 0 ] || fail "run this with sudo"
    if has_systemd && [ -f "/etc/systemd/system/$SERVICE.service" ]; then
        systemctl disable --now "$SERVICE" || true
        rm -f "/etc/systemd/system/$SERVICE.service"
        systemctl daemon-reload
    fi
    docker rm -f "$SERVICE" "$SERVICE-ingest" >/dev/null 2>&1 || true
    rm -f "$RUNNER"
    if [ "$KEEP_DATA" = "true" ]; then
        say "Stopped $NAME. The index and images are kept in $COLLECTION_DIR"
    else
        rm -rf "$COLLECTION_DIR"
        say "Removed $NAME and its data"
    fi
}

parse_args "$@"
case "$ACTION" in
install) do_install ;;
status) do_status ;;
describe) do_describe ;;
configure) do_configure ;;
update) do_update ;;
import) do_import ;;
uninstall) do_uninstall ;;
*) usage; exit 1 ;;
esac

exit 0
}
