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
FETCH_VIA=""
ANONYMOUS="false"
LIMIT=""
PORT="8000"
KEEP_DATA="false"
AS_JSON="false"
COLLECTION_FILE=""
COLLECTION_BASE64=""
IMAGE_WAS_GIVEN="false"

# The container runs as this user id, so the data folder must belong to it.
CONTAINER_UID=1000

usage() {
    cat <<'EOF'
Usage: bootstrap.sh <install|status|describe|update|uninstall> --name NAME [options]

install options:
  --source SRC        a folder, s3://bucket/prefix, or a .parquet manifest (required)
  --fetch-via S3URI   where the files live when manifest URLs are not downloadable
  --anonymous         read S3 without credentials (public buckets)
  --limit N           only index the first N images
  --port PORT         port for the site (default 8000)
  --image IMAGE       container image to run
  --image-tar FILE    load the image from a file instead of downloading it
  --data-root DIR     where collections are stored (default /opt/dce)
  --collection-file FILE  the collection.json that describes the collection to visitors

status options:
  --json              print the full report as JSON

describe options:
  --collection-file FILE  replace the collection.json of a running site. No restart needed.

update options:
  --image IMAGE       switch the site to this image. The index is kept.

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
        --fetch-via) FETCH_VIA="$2"; shift 2 ;;
        --anonymous) ANONYMOUS="true"; shift ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --image) IMAGE="$2"; IMAGE_WAS_GIVEN="true"; shift 2 ;;
        --image-tar) IMAGE_TAR="$2"; shift 2 ;;
        --data-root) DATA_ROOT="$2"; shift 2 ;;
        --keep-data) KEEP_DATA="true"; shift ;;
        --json) AS_JSON="true"; shift ;;
        --collection-file) COLLECTION_FILE="$2"; shift 2 ;;
        --collection-base64) COLLECTION_BASE64="$2"; shift 2 ;;
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
    -p $PORT:8000 -e DCE_COLLECTION=$NAME \\
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

image_in_use() { grep -oE '"[^"]+" (ingest|serve)' "$RUNNER" | head -1 | cut -d'"' -f2; }
port_in_use() { grep -oE '\-p [0-9]+:8000' "$RUNNER" | grep -oE '[0-9]+' | head -1; }

do_update() {
    [ "$(id -u)" -eq 0 ] || fail "run this with sudo"
    [ -f "$RUNNER" ] || fail "no collection named $NAME in $DATA_ROOT"
    [ "$IMAGE_WAS_GIVEN" = "true" ] || fail "--image is required"
    local current
    current="$(image_in_use)"
    fetch_image
    sed -i "s|\"$current\"|\"$IMAGE\"|g" "$RUNNER"
    if has_systemd; then
        systemctl restart "$SERVICE"
    else
        docker rm -f "$SERVICE" >/dev/null 2>&1 || true
        nohup "$RUNNER" >"$COLLECTION_DIR/runner.log" 2>&1 &
    fi
    say "Switched $NAME from $current to $IMAGE. The index was kept."
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
update) do_update ;;
uninstall) do_uninstall ;;
*) usage; exit 1 ;;
esac

exit 0
}
