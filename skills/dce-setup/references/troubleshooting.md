# Troubleshooting

## "already holds an index that this tool did not create"

`ingest` found `embeddings.pt` in the target folder without its own state file.
Someone built that index another way. Use a different `--data-dir`. Only pass
`--overwrite` when the person has explicitly said to replace that index.

## The report says image files could not be read

The manifest's URL column does not return image data. Open one URL to confirm:
it is usually a landing page. Find out where the files are actually stored and
pass `--fetch-via s3://bucket`. The object key is taken from the URL path.

## Download speed is much slower than expected

The `transfer` time in the profile is measured from this machine to the source.
Concurrency rarely helps when the link itself is the limit. For large remote
collections the realistic options are: run overnight (the run can be resumed),
index a sample first, or run on a cloud machine in the same region as the data.
The last option costs money and may conflict with data residency rules, so ask.

## Many images fail with "decode" errors

Check `problems` in the ingest summary. `UnidentifiedImageError` means the file
is not a real image despite its extension. `Truncated File Read` means the file
is incomplete. Both are problems in the source data, not in the tool. Report
the count and a few file names so the person can look into them.

## Images larger than 200 MB are skipped

This is deliberate, to protect memory. Raise it with `--max-file-mb` only when
`memory_bytes` from the environment check is comfortably larger than the files.

## The site starts but shows no results

Confirm the server was started with `DCE_DATA_DIR` pointing at the same folder
that was given to `--data-dir`. Without it the server reads the folders named in
`config.json`.

## Port 8000 is already in use

The server refuses to start and suggests another port. Another collection is
probably being served there: `curl -s http://localhost:8000/api/health` shows
which one. Leave it running and start this collection with `DCE_PORT=8001` (or
the next free port). Only stop the other server if the person asks you to.

## `ModuleNotFoundError` for boto3 or duckdb

Run `venv/bin/pip install -r requirements.txt`. These two packages are needed
for S3 and parquet sources.
