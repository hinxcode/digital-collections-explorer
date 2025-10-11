# Digital Collections Explorer

[![DOI](https://zenodo.org/badge/917426819.svg)](https://zenodo.org/badge/latestdoi/917426819)

A web-based exploratory search system leveraging CLIP (Contrastive Language-Image Pre-training) models for enhanced discovery of digital collections, including maps, photographs, and born-digital documents.

## Overview

This project describes out Digital Collections Explorer, available at: [https://arxiv.org/abs/2507.00961](https://arxiv.org/abs/2507.00961).

![A diagram showing an overview of our Digital Collections Explorer, including its various components.](https://github.com/hinxcode/digital-collections-explorer/blob/main/overview.png)

We present Digital Collections Explorer, a web-based, open-source exploratory search platform that leverages CLIP (Contrastive Language-Image Pre-training) for enhanced visual discovery of digital collections. Our Digital Collections Explorer can be installed locally and configured to run on a visual collection of interest on disk in just a few steps. Building upon recent advances in multimodal search techniques, our interface enables natural language queries and reverse image searches over digital collections with visual features. An overview of our system can be seen in the image above.

## Features

- Multimodal search capabilities using both text and image inputs
- Support for various digital collection types:
  - Historical maps
  - Photographs
  - Born-digital documents
- Fine-tuned CLIP models for improved accuracy (coming soon)
- User-friendly web interface for exploration

## Quick Start Guide

### Prerequisites

- Python 3.8+ 
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
python -m src.models.clip.generate_embeddings
```

This will process all images found in `raw_data_dir` and create embeddings in `embeddings_dir` (both set in `config.json`).

### Step 5: Start the Backend Server

```bash
python -m src.backend.main
```

The API server will start at http://localhost:8000

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

## References

Mahowald, J., & Lee, B. C. G. (2024). Integrating Visual and Textual Inputs for Searching Large-Scale Map Collections with CLIP. arXiv:2410.01190 [cs.IR]. https://arxiv.org/abs/2410.01190
