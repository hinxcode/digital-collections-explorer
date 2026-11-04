# Digital Collections Explorer

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.15744570.svg)](https://doi.org/10.5281/zenodo.15744570) [![Paper](https://img.shields.io/badge/paper-Computational%20Humanities%20Research-blue.svg)](https://doi.org/10.1017/chr.2025.10017) [![arXiv](https://img.shields.io/badge/arXiv-2507.00961-b31b1b.svg)](https://arxiv.org/abs/2507.00961)

**Digital Collections Explorer is an open-source search site for image collections that have little or no metadata.** A library, archive or museum points it at a folder, an S3 bucket or a manifest of images. Visitors can then search the collection in plain language ("a steam locomotive", "a handwritten letter with a red seal"), search with a picture, wander through it, and follow every image back to the institution's own record. No catalog, tags or OCR are needed, and where a catalog exists, search reads its records too.

The [project site](https://digital-collections-explorer.com/) has a live demo and the documentation. The software is built by the [Lab for Computing Cultural Heritage](https://l4cch.github.io/lab-website/) at the University of Washington Information School and is described in [our paper in *Computational Humanities Research*](https://doi.org/10.1017/chr.2025.10017).

![A diagram showing an overview of our Digital Collections Explorer, including its various components.](overview.png)

## Quick Start

You need Python 3.10 or later and Node.js 20.19 or later.

```bash
git clone https://github.com/hinxcode/digital-collections-explorer.git
cd digital-collections-explorer
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
npm install && npm run setup -- --type=photographs   # or maps, documents

python -m src.ingest /path/to/images --data-dir data/collections/my-collection
DCE_DATA_DIR=data/collections/my-collection python -m src.backend.main
```

Then open http://localhost:8000. The images can also come from an S3 prefix (add `--anonymous` for a public bucket) or a parquet manifest of image addresses, and `python -m src.profiling <source>` says beforehand what the collection holds and what indexing will cost. Indexing can be stopped and run again; it continues where it left off. Search uses SigLIP by default; SigLIP 2 and CLIP can be chosen in `config.json`.

PDFs, for the `documents` interface, are indexed page by page with the older tool: put them in `data/raw`, run `python -m src.models.generate_embeddings`, then `python -m src.backend.main`.

## Other Ways to Start

With an AI coding agent such as Claude Code, Codex, Gemini CLI or Cursor, ask it to make your collection searchable. The `dce-setup` skill in `skills/` walks it through profiling, indexing and serving.

With Docker, one command builds the index and another serves it. The image is built for x86-64, so on Apple Silicon Docker runs it under emulation.

```bash
docker run --rm -v "$PWD/my-collection:/data" -v /path/to/images:/source:ro ghcr.io/hinxcode/digital-collections-explorer ingest /source
docker run -p 8000:8000 -v "$PWD/my-collection:/data" ghcr.io/hinxcode/digital-collections-explorer
```

On a Linux server, `deploy/bootstrap.sh` installs everything, indexes and keeps the site running across reboots. On AWS, `deploy/aws/deploy.sh` does the same on a machine it creates, after showing what it will cost.

```bash
sudo deploy/bootstrap.sh install --name my-collection --source /path/to/images
deploy/aws/deploy.sh my-collection --source s3://bucket/prefix --anonymous --https
```

## What It Does

- **Searches by meaning.** Natural-language queries and reverse image search over photographs, maps and PDFs, with an interface for each: `photographs`, `maps` and `documents`.
- **Needs no metadata, and uses it when it exists.** A catalog groups images into objects, links each one to its record, and makes the records searchable beside the pictures.
- **Scales on ordinary hardware.** Indexing reads from disk, S3 or a manifest without copying the originals, and serving needs no GPU.
- **Is safe to put online.** Rate, upload and concurrency limits protect a small machine, and every refusal is explained in plain words.
- **Can be searched by AI assistants.** An optional MCP server lets Claude, ChatGPT and other assistants search the collection and link back to it.

## Documentation

The [documentation](https://digital-collections-explorer.com/docs/) covers:

- [Indexing large or remote collections](https://digital-collections-explorer.com/docs/indexing/)
- [Describing a collection to visitors](https://digital-collections-explorer.com/docs/describing-a-collection/)
- [Collections split into groups](https://digital-collections-explorer.com/docs/groups/)
- [Searching by appearance and by catalog](https://digital-collections-explorer.com/docs/search/)
- [Models: SigLIP, SigLIP 2 and CLIP](https://digital-collections-explorer.com/docs/models/)
- [Limits that protect a public site](https://digital-collections-explorer.com/docs/limits/)
- Deploying [to a Linux server](https://digital-collections-explorer.com/docs/deploy/server/), [to AWS](https://digital-collections-explorer.com/docs/deploy/aws/), or [under a path of an existing website](https://digital-collections-explorer.com/docs/deploy/under-a-path/)
- [The MCP server for AI assistants](https://digital-collections-explorer.com/docs/mcp-server/)

## Citation

If you use Digital Collections Explorer in research, please cite the paper and the software release you used. Every release has its own DOI on [Zenodo](https://doi.org/10.5281/zenodo.15744570). The paper is open access in [*Computational Humanities Research*](https://doi.org/10.1017/chr.2025.10017), and the preprint is on [arXiv](https://arxiv.org/abs/2507.00961).

```bibtex
@article{huang2025digitalcollectionsexplorer,
  title   = {Digital Collections Explorer: An Open-Source, Multimodal Viewer for Searching Digital Collections},
  author  = {Huang, Ying-Hsiang and Lee, Benjamin Charles Germain},
  journal = {Computational Humanities Research},
  volume  = {1},
  pages   = {e14},
  year    = {2025},
  doi     = {10.1017/chr.2025.10017}
}
```

## License

The source code of Digital Collections Explorer is licensed under the [MIT License](LICENSE). Documentation and original figures, such as `overview.png`, are licensed under [CC BY 4.0](LICENSE-CC-BY-4.0) unless otherwise noted. Third-party code, models, data and media keep their respective licenses.

## Contributing

Contributions are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers setting up for development, running the tests and sending a change, and the project follows a [Code of Conduct](CODE_OF_CONDUCT.md).
