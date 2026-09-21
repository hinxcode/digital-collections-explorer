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
   embeddings". Say "memory", not "RAM". Give times and sizes in human units
   (minutes, MB), never bytes or milliseconds. Never show the person internal
   names or raw output: no field names such as `capture_date`, no "EXIF" (say
   "the date stored inside each photo file"), no process ids, no JSON, and no
   raw error messages. Translate an error into what happened and what it means
   for them, for example "2 files are damaged and could not be opened".
8. **Report measurements, not guesses.** Numbers in the profile's `sizing` are
   estimates made before indexing. After indexing, report only measured values
   from the ingest summary. If you must quote an estimate, call it an estimate.

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
   images with no catalog record, non-image files, or damaged files. If the
   report lists files that may be a catalog (spreadsheets, CSV), mention them.
   Say plainly when one looks empty. Say honestly that a catalog file is not
   used yet, so the person does not expect its contents to appear in the site.
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
`recommended` answer, and `why`.

- **Small local job** (the estimate is under five minutes, the source is on this
  machine, and nothing costs money): go ahead with the recommended answers, then
  tell the person what you chose and why, so they can object. Skip the question
  about storing data in the cloud, since nothing leaves their machine.
- **Anything larger, remote, or costing money:** ask first. Ask the questions
  together, in plain language, showing the recommendation and the reason. If
  your environment has a structured question tool, use it. Accept "whatever you
  recommend" as an answer.

Add one question of your own when it applies: if indexing will take more than
an hour, ask whether to index a small sample first (a few hundred images) so
they can see the result in minutes before committing to the full run.

## Step 5. Build the index

Give each collection its own folder under `data/collections/`:

```bash
$PY -m src.ingest SOURCE --data-dir data/collections/NAME \
  --estimated-seconds SECONDS --json data/collections/NAME/ingest_summary.json
```

`SECONDS` is `sizing.embed_seconds.estimated` from the profile. Passing it lets the
final report compare the estimate with what really happened.

`SOURCE` and the `--anonymous` and `--fetch-via` flags are the same as in step 2.
Add `--limit N` for a sample run.

- Runs longer than a few minutes should go in the background. Check progress
  with `$PY -m src.ingest --status --data-dir data/collections/NAME`.
- It is safe to stop at any time. Running the same command again continues
  where it left off.
- Original images are streamed and never stored. Only small copies are kept.
- A few failures are normal in real collections. Report the count and the
  reasons from `problems`. Investigate only if failures exceed a few percent.
- `$PY -m src.ingest --report --data-dir data/collections/NAME` prints how the run
  went in plain words at any time, including for a run that finished long ago.

## Step 6. Start the site

The summary's `serve_command` is the command to run. Port 8000 is the default.
If the server reports that the port is already in use, another collection is
probably being served there. Leave it running and pick the next free port with
`DCE_PORT`. Never stop a server you did not start without asking.

```bash
DCE_DATA_DIR=data/collections/NAME DCE_PORT=8000 $PY -m src.backend.main
```

Run it in the background, then check that the site is up **and that it is
serving this collection**, not someone else's server on the same port:

```bash
curl -s http://localhost:8000/api/health
```

`collection` must equal `NAME`, and `items` must equal `indexed` from the ingest
summary. Then confirm search works before telling the person it is ready:

```bash
curl -s "http://localhost:8000/api/search/text?query=a%20portrait&limit=3"
```

### Describe the collection to visitors

Until a `collection.json` sits in `data/collections/NAME/`, the site shows a generic
title and no suggested searches. Write one with the person, starting from
`collection.example.json`: the title, one or two sentences of introduction, the name
of the institution, the licence, and six to eight example searches. Only suggest
searches you have run and that return good results. The site reads the file on every
visit, so no restart is needed. On a deployed site, deliver it with
`deploy/bootstrap.sh describe` or `deploy/aws/describe.sh NAME --file collection.json`.

## Step 7. Tell the person how it went

People have to account for their time and money. When indexing has finished, tell
them, from the `run` section of the ingest summary and nothing else:

1. How long indexing took, and how that compares with the estimate you gave.
2. How many images were indexed, skipped and failed. Name the failed files from
   `run.failed_files` so they can look into them.
3. How much disk the collection now uses, from `disk_bytes_measured`.
4. What it cost and what it costs from now on. On a cloud deployment
   `deploy/aws/status.sh NAME` works this out from current prices, including the
   cost per 1,000 images. On their own machine, say that it cost nothing extra.
5. If `status.sh` prints a WARNING about a large machine still running, pass it on
   first. It is the one thing in the report that keeps costing money.

Give them the address (for example `http://localhost:8000`) and two or three example
searches suited to their collection. Suggest describing what a picture looks
like rather than typing catalog terms, since the search reads the images
themselves.

## When something goes wrong

See [references/troubleshooting.md](references/troubleshooting.md).

## Putting the site on a server or on AWS

Only when the person asks for it. The README section "Deploying to a Server or to AWS"
has the commands. `deploy/bootstrap.sh install` turns any Linux machine into the site.
`deploy/aws/deploy.sh NAME --source ...` creates one AWS machine, and the images must
already be reachable from the cloud (an `s3://` or `https://` address).

`deploy.sh` lists what it will create and what that costs per month, then waits for
`yes`. Show the person that list and let them answer. Never pass `--yes` for them
(ground rule 5). Afterwards `status.sh` reports progress and cost, `describe.sh` and
`configure.sh` change the description and the limits, `update.sh` switches versions,
and `destroy.sh` removes everything. Add `--https` only for a site meant for the public.

## Not available yet

Be honest if asked for these. They are planned, not built:

- Publishing to Hugging Face Spaces, or to a cloud other than AWS.
- The site's own domain name. `--https` gives it a CloudFront address instead.
- Changing the layout of the search site.
- Filters in the search site. The report lists which filters the data supports,
  but the site does not show them yet.
