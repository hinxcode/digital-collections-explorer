---
name: dce-setup
description: Turn a folder, S3 bucket, or parquet manifest of images into a searchable visual collection with Digital Collections Explorer. Use when someone wants to explore, search, index, or publish an image collection, including collections with no metadata, no catalog, and messy file names. Inspects the collection, explains what is and is not possible, asks only the questions a person must answer, builds the search index, and starts the search site.
license: MIT
compatibility: Run from the root of the digital-collections-explorer repository. Needs Python 3.10+ and a shell. Needs network access for S3 or remote manifests.
metadata:
  author: digital-collections-explorer
  version: "0.1"
---

# Set up a searchable collection

The person you are helping is probably a curator, librarian, or researcher, not
an engineer. They know their collection. They do not know what a GPU, an
embedding, or a batch size is, and they should never need to.

Your job is to take them from "the images are over there" to a working search
site, making every technical decision yourself and asking them only what a
machine cannot find out.

## Ground rules

1. **Measure, do not ask.** Hardware, disk space, file counts, formats, download
   speed, and available metadata are all measured by the commands below. Never
   ask the person for something a command can tell you.
2. **Ask only what a person must decide.** These are policy and intent: may the
   data leave their machines, who is the site for, should uncatalogued images be
   included. Each question needs a recommended answer and a one-sentence reason.
3. **Say what is not possible, and why.** If the collection has no dates, say
   there will be no date filter and explain what it would take to get one. Do
   not quietly leave it out and do not promise it.
4. **Never replace an existing index.** If `ingest` refuses because an index
   already exists, choose a new `--data-dir`. Do not pass `--overwrite` unless
   the person explicitly asks to replace that specific index.
5. **Never spend money without consent.** Before creating any cloud resource,
   state the monthly cost and wait for a clear yes.
6. **Keep the three kinds of information apart.** A field is either from the
   institution's catalog, read from the files (EXIF, file names, folders), or a
   machine guess. When you describe a field, say which. Never present a machine
   guess as catalog fact.
7. **Use plain language.** Say "analysing the images", not "computing
   embeddings". Say "memory", not "RAM". Give times and sizes in human units.

## Python

Use the repository's virtual environment when it exists:

```bash
PY=venv/bin/python; [ -x "$PY" ] || PY=python
```

If imports fail, install the dependencies first:

```bash
python -m venv venv && venv/bin/pip install -r requirements.txt
```

## Step 1. Look at the machine

```bash
$PY -m src.environment
```

This prints JSON. Note `device`, `memory_bytes`, `free_disk_bytes`,
`aws_credentials_found`, `existing_index`, and `frontend_built`. Do not show the
JSON to the person. Use it to make decisions later.

If `frontend_built` is false, build it once:

```bash
npm install && npm run setup -- --type=photographs
```

## Step 2. Look at the collection

Pick the form that matches what the person gave you:

```bash
$PY -m src.profiling /path/to/folder --json /tmp/profile.json
$PY -m src.profiling s3://bucket/prefix --anonymous --json /tmp/profile.json
$PY -m src.profiling manifest.parquet --json /tmp/profile.json
```

Use `--anonymous` for public buckets. Leave it off when
`aws_credentials_found` is true and the bucket is private.

Read both the printed report and `/tmp/profile.json`.

**If the report warns that image files could not be read**, stop and fix that
first. The usual cause is a manifest whose URL column points to web pages rather
than files. Ask where the actual files are stored, then rerun with
`--fetch-via s3://bucket`. Estimates are meaningless until this is resolved.

## Step 3. Tell the person what you found

Summarise the report in a few short paragraphs, in this order:

1. What is there: how many images, how large, and anything surprising such as
   images with no catalog record, non-image files, or damaged files.
2. What they will be able to do: search by description, search by example
   image, and each available filter with where it comes from.
3. What they will not be able to do, with the reason for each, and what it
   would take to change that.
4. What it will cost: time to build, disk space needed, and whether their
   machine can handle it. Compare `sizing` in the profile against
   `free_disk_bytes` and `memory_bytes` from step 1. If it does not fit, say so
   now.

Be careful with dates and places read from the image files. EXIF records when
and where a picture was taken. For a born-digital photo archive that is the real
date. For scanned documents or photographed museum objects it is the
digitisation date and the studio, which is rarely what a curator means by
"date". Say which case applies, and ask if you cannot tell.

Lead with whatever would surprise them most. A curator learning that most of
their images have no catalog record matters more than the file count.

## Step 4. Ask the decisions

The profile's `decisions` list holds the questions, each with `options`, a
`recommended` answer, and `why`. Ask them together, in plain language, showing
the recommendation and the reason. If your environment has a structured
question tool, use it. Accept "whatever you recommend" as an answer.

Add one question of your own when it applies: if indexing will take more than
an hour, ask whether to index a small sample first (a few hundred images) so
they can see the result in minutes before committing to the full run.

## Step 5. Build the index

Give each collection its own folder under `data/collections/`:

```bash
$PY -m src.ingest SOURCE --data-dir data/collections/NAME --json data/collections/NAME/ingest_summary.json
```

`SOURCE` and the `--anonymous` and `--fetch-via` flags are the same as in step 2.
Add `--limit N` for a sample run.

- Runs longer than a few minutes should go in the background. Check progress
  with `$PY -m src.ingest --status --data-dir data/collections/NAME`.
- It is safe to stop at any time. Running the same command again continues
  where it left off.
- Original images are streamed and never stored. Only small copies are kept.
- A few failures are normal in real collections. Report the count and the
  reasons from `problems`. Investigate only if failures exceed a few percent.

## Step 6. Start the site

The summary's `serve_command` is the exact command to run:

```bash
DCE_DATA_DIR=data/collections/NAME $PY -m src.backend.main
```

Run it in the background, wait for `GET /api/health` to return healthy, then
confirm search works before telling the person it is ready:

```bash
curl -s "http://localhost:8000/api/search/text?query=a%20portrait&limit=3"
```

Give them the address (`http://localhost:8000`) and two or three example
searches suited to their collection. Suggest describing what a picture looks
like rather than typing catalog terms, since the search reads the images
themselves.

## When something goes wrong

See [references/troubleshooting.md](references/troubleshooting.md).

## Not available yet

Be honest if asked for these. They are planned, not built:

- Publishing the site to the cloud or to Hugging Face Spaces.
- Changing the layout of the search site.
- Grouping results so several photos of one object appear as one result.
- Filters in the search site. The report lists which filters the data supports,
  but the site does not show them yet.
