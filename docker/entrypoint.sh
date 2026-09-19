#!/bin/sh
set -e

command="${1:-serve}"
if [ $# -gt 0 ]; then
    shift
fi

case "$command" in
serve)
    if [ ! -f "$DCE_DATA_DIR/embeddings/embeddings.pt" ]; then
        echo "No search index found in $DCE_DATA_DIR."
        echo "Build one first, with the same folder mounted at $DCE_DATA_DIR:"
        echo "  docker run --rm -v <collection-folder>:$DCE_DATA_DIR -v <images>:/source:ro <image> ingest /source"
        exit 1
    fi
    exec python -m src.backend.main "$@"
    ;;
ingest)
    exec python -m src.ingest "$@"
    ;;
profile)
    exec python -m src.profiling "$@"
    ;;
*)
    exec "$command" "$@"
    ;;
esac
