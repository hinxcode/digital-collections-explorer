# Digital Collections Explorer

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.15744570.svg)](https://doi.org/10.5281/zenodo.15744570)
[![arXiv](https://img.shields.io/badge/arXiv-2507.00961-b31b1b.svg)](https://arxiv.org/abs/2507.00961)

**Digital Collections Explorer is an open-source search site for image collections that have little or no metadata.** A library, archive or museum points it at a folder, an S3 bucket or a manifest of images. Visitors can then search the collection in plain language ("a steam locomotive", "a handwritten letter with a red seal"), search with a picture, wander through it, and follow every image back to the institution's own record. No catalog, tags or OCR are needed: search compares the meaning of the words with the content of the images, using a multimodal embedding model (SigLIP by default, CLIP optionally).

It indexes hundreds of thousands of images on ordinary hardware, serves them from one small machine without a GPU, and can be installed locally or deployed to a server or AWS with one command. A public demo runs at [digital-collections-explorer.com](https://digital-collections-explorer.com/).

The software is built by the [Lab for Computing Cultural Heritage](https://l4cch.github.io/lab-website/) at the University of Washington Information School and is described in [our paper](https://arxiv.org/abs/2507.00961). To cite it, see [Citation](#citation).

![A diagram showing an overview of our Digital Collections Explorer, including its various components.](https://github.com/hinxcode/digital-collections-explorer/blob/main/overview.png)

## Three Ways to Start

| You have | Do this |
| --- | --- |
| An AI coding agent (Claude Code, Codex, Gemini CLI, Cursor) | Ask it to make your collection searchable. The `dce-setup` skill in `skills/` walks it through profiling, indexing and serving. See [Large, Remote, or Unsorted Collections](#large-remote-or-unsorted-collections). |
| Docker | Two commands: one to build the index, one to serve it. See [Running with Docker](#running-with-docker). |
| A Linux server or an AWS account | One command that installs everything, indexes, serves and survives reboots. AWS deployments show their cost before creating anything. See [Deploying to a Server or to AWS](#deploying-to-a-server-or-to-aws). |
| A laptop and Python | The [Quick Start Guide](#quick-start-guide) below. |

## What It Does

- **Searches by meaning.** Natural-language queries and reverse image search over photographs, maps and born-digital documents (PDFs), in one interface.
- **Needs no metadata.** Uncataloged collections work as they are. When a catalog exists, its columns group images into objects and link each image back to the original record.
- **Comes with three interfaces.** `photographs` opens on a wall of images to wander through and gives every image its own page. `maps` adds a lightbox and image upload. `documents` previews and searches PDFs page by page.
- **Scales on ordinary hardware.** Indexing is resumable and reads from disk, S3 or a parquet manifest without copying the originals. Serving needs no GPU.
- **Is safe to put on the internet.** Rate limits, upload limits and concurrency limits protect a small machine. Every refusal is explained to the visitor in plain words.
- **Describes itself to visitors and to machines.** A `collection.json` sets the title, introduction and suggested searches. The site fills its page title, description and social-sharing tags from it and serves `robots.txt` and `llms.txt`, so search engines and AI assistants can find and describe your collection.

## How It Differs

- **From a catalog search:** a catalog finds what someone has already described. Digital Collections Explorer finds what is in the image, so it works on the boxes nobody has had time to catalog.
- **From an image viewer (IIIF, Mirador):** viewers display images that were found some other way. This is the finding part, and it links out to your existing viewer or record.
- **From a hosted AI search service:** this runs on your own machine or cloud account. Your images never leave it, there is no per-query fee, and the code is open.

## Quick Start Guide

### Prerequisites

- Python 3.10+
- Node.js 14+
- Git
- Docker (optional, for containerized deployment)

### Step 1: Clone the Repository

```bash
git clone https://github.com/hinxcode/digital-collections-explorer.git
cd digital-collections-explorer
```

### Step 2: Run the Setup Script with Collection Type

```bash
npm install
npm run setup -- --type=photographs
```

Available collection types:

- `photographs`: For photo collections and image archives
- `maps`: For map collections
- `documents`: For born-digital documents collections

This will configure the project for your specific collection type and build the frontend.

### Step 3: Set Up the Environment for the Backend

```bash
# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 4: Prepare Your Collection

1. Add your images to the directory configured as `raw_data_dir` (default: `data/raw`). Supported formats include JPG, JPEG, PNG, GIF, BMP, TIFF, and WebP. The images in subdirectories will also be retrieved recursively.

2. Generate embeddings for your collection:

```bash
python -m src.models.generate_embeddings
```

This will process all images found in `raw_data_dir` and create embeddings in `embeddings_dir` (both set in `config.json`).

### Step 5: Start the Backend Server

```bash
python -m src.backend.main
```

The API server will start at http://localhost:8000

## Large, Remote, or Unsorted Collections

The steps above expect your images in `data/raw`. When a collection is too large for
your disk, lives in an S3 bucket, or has never been organized, use the tools below
instead. They need no metadata and never store the original images.

```bash
# 1. See what the collection contains, what is possible, and what indexing will cost
python -m src.profiling /path/to/images
python -m src.profiling s3://bucket/prefix --anonymous
python -m src.profiling manifest.parquet --fetch-via s3://bucket

# 2. Build the index. Safe to stop and rerun; it continues where it left off.
python -m src.ingest /path/to/images --data-dir data/collections/my-collection

# 3. Serve that collection
DCE_DATA_DIR=data/collections/my-collection python -m src.backend.main
```

If you use an AI coding agent that supports [Agent Skills](https://agentskills.io)
(Claude Code, Codex, Gemini CLI, Cursor, and others), the `dce-setup` skill in
`skills/` walks through these steps for you. Ask it to make your collection searchable.

## Running with Docker

Building the index is a one-off job. Serving searches is a long-running service that
does not need a GPU. The image supports both, so they can run on different machines.

```bash
docker build -t digital-collections-explorer .

# Build the index once. The collection folder keeps the index, thumbnails and state.
docker run --rm \
  -v "$PWD/data/collections/my-collection:/data" \
  -v /path/to/images:/source:ro \
  digital-collections-explorer ingest /source

# Serve it
docker run -p 8000:8000 \
  -v "$PWD/data/collections/my-collection:/data" \
  digital-collections-explorer
```

The same two steps with Docker Compose:

```bash
SOURCE_DIR=/path/to/images COLLECTION=my-collection docker compose run --rm ingest
COLLECTION=my-collection docker compose up serve
```

Build options:

- `--build-arg COLLECTION_TYPE=maps` selects the frontend (`photographs`, `maps`, `documents`).
- `--build-arg TORCH_VARIANT=cu124` installs the CUDA build of PyTorch for indexing on a
  GPU. The default is the much smaller CPU build, which is all that serving needs.
- `--build-arg PRELOAD_MODEL=false` leaves the model out of the image. It is then
  downloaded each time a container starts.

## Describing Your Collection to Visitors

The photographs site opens on a wall of images to wander through, suggests searches,
shows each object once however many photos it has, and gives every image its own page
with similar images and a link back to the institution's own record.

Put a `collection.json` next to the index (in the folder you pass to `--data-dir`) to
set the title, the introduction, the suggested searches, the license and the footer
links. `collection.example.json` shows every field. All of them are optional. The site
reads the file on every visit, so a change shows up without a restart. For a deployed
site, see `--collection-file` and `describe` below.

The link back to the original record is taken from the catalog: a column named
`source_url`, `guid`, `record_url`, `landing_page` or `permalink` that holds a web
address. Images are grouped into objects by a column named `object_id`, `record_id`,
`item_id` or `group_id`. Collections without a catalog still work: every image is
then its own object and is shown as uncataloged.

## Limits That Protect a Public Site

Searching is the only expensive thing the site does, so it is the only thing that is
limited. Browsing and viewing images are not. The defaults suit a small machine:

| Setting | Default | Meaning |
| --- | --- | --- |
| `max_upload_mb` | 10 | Largest image a visitor may search with |
| `searches_per_minute` | 60 | Searches one visitor may run per minute. 0 turns this off |
| `concurrent_searches` | 2 | Searches that use the model at once. Others wait up to 15 seconds, then are asked to try again |
| `proxy_hops` | 0 | Proxies in front of the site that add the visitor's address to `X-Forwarded-For`. Leave at 0 unless there is one, or visitors could pose as each other |

A visitor who is turned away is told why, in plain words. To change a limit, put it in
`settings.json` next to the index, or run one of these. The site picks it up without a restart.

```bash
DCE_DATA_DIR=data/collections/my-collection python -m src.backend.core.site_settings max_upload_mb=20
sudo deploy/bootstrap.sh configure --name my-collection --set max_upload_mb=20
deploy/aws/configure.sh my-collection --set max_upload_mb=20
```

## Deploying to a Server or to AWS

### Any Linux machine

`deploy/bootstrap.sh` turns a Linux machine into a collection site with one command.
It works the same on a cloud VM, a server in your own machine room, or a laptop. It
installs Docker if needed, builds the index once, then serves the site and keeps it
running across reboots.

```bash
sudo deploy/bootstrap.sh install --name my-collection --source /path/to/images
sudo deploy/bootstrap.sh status --name my-collection
sudo deploy/bootstrap.sh uninstall --name my-collection   # add --keep-data to keep the index
```

Indexing can be interrupted. It continues where it left off the next time the machine starts.

Add `--collection-file collection.json` to `install` to give the site its title,
introduction and suggested searches from the start. To change them later, while the
site keeps running:

```bash
sudo deploy/bootstrap.sh describe --name my-collection --collection-file collection.json
```

### Under a path on an existing website

A site can also live at a path such as `https://library.example.org/maps/`. Set
`DCE_BASE_PATH`, or `--base-path` with the bootstrap script, or `BASE_PATH` with Docker
Compose. The proxy configuration and the `robots.txt` to add at the root of the domain are
covered in the [documentation](https://digital-collections-explorer.com/docs/deploy/under-a-path/).

### AWS

`deploy/aws/` creates one small EC2 machine that runs the same bootstrap script. Before
creating anything it lists what it will create and looks up the current AWS prices,
and it does nothing until you type `yes`.

```bash
deploy/aws/deploy.sh my-collection --source s3://bucket/prefix --anonymous
deploy/aws/status.sh my-collection
deploy/aws/destroy.sh my-collection     # removes everything it created
```

To change a deployment, run `deploy.sh` again with the same name and only the options
you want to change. Everything you leave out keeps its current value, and the script
lists what will change before it asks you to confirm.

Indexing is the only heavy work, so it pays to index on a large machine and serve from a
small one. Changing `--instance-type` restarts the machine as the new type and keeps its
index and its address.

```bash
deploy/aws/deploy.sh my-collection --source s3://bucket/prefix --anonymous --instance-type c7i.2xlarge
# ...once status.sh reports that indexing has finished:
deploy/aws/deploy.sh my-collection --instance-type t3.medium
```

The script never lets an update replace the machine, which would delete the index: it
keeps the machine's operating system image fixed and refuses to change the disk size.
It also refuses to change the options that only matter when a machine is first created
(`--source`, `--fetch-via`, `--anonymous`, `--limit`, `--image`, `--bootstrap-url`),
because that would restart the machine and change nothing. To switch a running site to
another version, use `update.sh` below.

`status.sh` reports how the run went and what it cost: when indexing started and
finished, how long it took, images per second, how much was read from the source, the
files that failed, the cost of the run at current AWS prices, the cost per 1,000 images,
and what the machine costs per month from now on. It warns when a large machine is
still running after indexing has finished. Locally, `python -m src.ingest --report
--data-dir ...` prints the same report, also for a run that finished long ago.

`deploy.sh` takes the same `--collection-file collection.json`. To change the
description of a site that is already deployed, without touching the machine or the index:

```bash
deploy/aws/describe.sh my-collection --file collection.json
```

To open the site to the public, add `--https`. The site then gets an `https://` address
from CloudFront, with no domain name or certificate to arrange, and the machine stops
accepting traffic from anywhere else. CloudFront also keeps copies of the images, which
takes most of the load off a small machine. It is free up to 1 TB and 10 million requests
a month. `--no-https` turns it off again. `--https` cannot be combined with
`--allowed-cidr`, which is for sites that should stay internal.

```bash
deploy/aws/deploy.sh my-collection --https
```

To move a deployed site to a newer version without indexing again:

```bash
deploy/aws/update.sh my-collection --image ghcr.io/hinxcode/digital-collections-explorer:next
```

The images must already be reachable from the cloud (an `s3://` or `https://` address).
There is no SSH: administrators connect through AWS Session Manager. Pass `--budget` and
`--email` to be warned when the monthly bill passes an amount you choose.

The same template (`deploy/aws/template.yaml`) can be launched from the AWS console.
Other clouds are not covered yet. The bootstrap script is cloud-neutral, so supporting
one means writing only the small part that creates a machine and runs it.

## Model Configuration

Configure the model in `config.json`:

### Using SigLIP (default)

[SigLIP](https://arxiv.org/abs/2303.15343) is an open-source multimodal embedding model created by Google DeepMind.

```json
{
  "model_config": {
    "model_type": "siglip",
    "model_name": "google/siglip-base-patch16-224",
    "device": "mps"
  }
}
```

In our tests on a museum collection it found clearly better matches than CLIP for
English queries, and it stays usable for queries in other languages, where CLIP mostly
fails. Search works best in English. It indexes about three times slower than CLIP and
its index is about 1.5 times larger.

### Using CLIP

```json
{
  "model_config": {
    "model_type": "clip",
    "model_name": "openai/clip-vit-base-patch32",
    "device": "mps"
  }
}
```

### Changing the model

An index can only be searched with the model that built it. The server checks this
when it starts and explains what to do if they differ. After changing the model,
build a new index.

**Device options:**

- `"mps"` - Apple Silicon GPU (M1/M2/M3/M4)
- `"cuda"` - NVIDIA GPU
- `"cpu"` - CPU only


## Unit tests

```
pytest
```

### Customizing the Frontend

#### Development Mode

For active development with hot-reloading:

```bash
# To enable auto-reloading of the backend server whenever code changes, first modify the `api_config.debug` setting in in `config.json` from `false` to `true`.
# Next, ensure the backend server is running. If the server is not yet running, navigate to the project's root directory and execute:
python -m src.backend.main

# Start the frontend development server
cd src/frontend/[photographs|maps|documents]
npm run dev
```

This will start a frontend dev server at http://localhost:5173 with hot-reloading enabled. The development server will automatically proxy API requests to the backend at http://localhost:8000.

#### Production Build

When you're ready to deploy your changes, and only if you have customized the frontend and made code changes, since Step 2 has already built the frontend once:

```bash
npm run frontend-build
```

Then restart the backend server to serve the updated frontend.

## Citation

If you use Digital Collections Explorer in research, please cite the paper and the software release you used. Every release has its own DOI on [Zenodo](https://doi.org/10.5281/zenodo.15744570).

```bibtex
@article{huang2025digitalcollectionsexplorer,
  title   = {Digital Collections Explorer: An Open-Source, Multimodal Viewer for Searching Digital Collections},
  author  = {Huang, Ying-Hsiang and Lee, Benjamin Charles Germain},
  journal = {arXiv preprint arXiv:2507.00961},
  year    = {2025},
  doi     = {10.48550/arXiv.2507.00961}
}
```

## Contributing

Contributions are welcome! We appreciate bug fixes, new features, and documentation improvements.

### Quick Start for Contributors

1. Fork and clone the repository
2. Create a feature branch: `git checkout -b feature/my-change`
3. Set up the environment following the Quick Start guide above
4. Make your changes and test locally
5. Run linting:
   - Python: `black . && isort .`
   - Frontend: `npm run lint` (in the frontend directory)
6. Commit with clear messages (Conventional Commits encouraged)
7. Open a Pull Request

For detailed guidelines, please read [CONTRIBUTING.md](CONTRIBUTING.md).

### Ways to Contribute

- 🐛 **Report bugs** using our [bug report template](.github/ISSUE_TEMPLATE/bug_report.md)
- ✨ **Suggest features** using our [feature request template](.github/ISSUE_TEMPLATE/feature_request.md)
- 📚 **Improve documentation** using our [documentation template](.github/ISSUE_TEMPLATE/documentation.md)
- 💻 **Submit code** via Pull Requests following our [PR template](.github/PULL_REQUEST_TEMPLATE.md)

### Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.
