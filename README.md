# Second Brain OCR

![CI/CD Pipeline](https://github.com/madebygps/second-brain-ocr/actions/workflows/ci-cd.yml/badge.svg)

Automated OCR and semantic search for your second brain notes. Watches directories for images, extracts text with Azure Document Intelligence, generates embeddings with Azure OpenAI, and indexes in Azure AI Search for semantic retrieval.

## Features

- Automated file watching with event-based monitoring and polling fallback
- OCR text extraction from images and PDFs
- Vector embeddings for semantic search
- State management to prevent reprocessing
- Docker-first deployment for Synology NAS or any Docker host
- CI/CD pipeline with automated testing and ACR deployment
- Optional webhook notifications for file processing events

## Prerequisites

Azure resources required:
- **Azure Document Intelligence** - OCR service
- **Azure OpenAI** - Embedding model deployment (text-embedding-3-large or text-embedding-ada-002)
- **Azure AI Search** - Free tier supports ~2,500 documents

## Quick Start

### Docker Deployment

```bash
git clone https://github.com/madebygps/second-brain-ocr.git
cd second-brain-ocr
cp .env.example .env
# Edit .env with Azure credentials
```

Update volume paths in `docker-compose.yml`:
```yaml
volumes:
  - /path/to/your/brain-notes:/brain-notes:ro
  - ./data:/app/data
```

Start the service:
```bash
docker-compose up -d
docker-compose logs -f
```

### Portainer Deployment

Images are automatically built and pushed to ACR on every commit to main. See [CI/CD setup guide](docs/CICD_SETUP.md) and [ACR deployment guide](ACR_DEPLOYMENT.md).

## Directory Structure

Organize notes with this structure:
```
brain-notes/
├── books/
│   └── atomic-habits/
│       ├── page1.jpg
│       └── page2.jpg
├── articles/
│   └── productivity-tips/
└── essays/
    └── philosophy-notes/
```

The app extracts metadata:
- **Category**: Top-level folder (books, articles, essays)
- **Source**: Subfolder name (atomic-habits)
- **Title**: Formatted source name (Atomic Habits)

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `WATCH_DIR` | Directory to monitor | `/brain-notes` |
| `POLLING_INTERVAL` | Polling interval in seconds | `180` |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | OCR endpoint | Required |
| `AZURE_DOC_INTELLIGENCE_KEY` | OCR key | Required |
| `AZURE_OPENAI_ENDPOINT` | OpenAI endpoint | Required |
| `AZURE_OPENAI_KEY` | OpenAI key | Required |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Model deployment name | `text-embedding-ada-002` |
| `AZURE_SEARCH_ENDPOINT` | Search endpoint | Required |
| `AZURE_SEARCH_KEY` | Search key | Required |
| `STATE_FILE` | Processed files tracker | `/app/data/processed_files.json` |
| `WEBHOOK_URL` | Notification webhook URL | None (disabled) |

See `.env.example` for all options.

## Notifications

Get notified when files are processed! Configure a `WEBHOOK_URL` to receive notifications via:
- **ntfy.sh** - Instant push notifications (no account needed)
- **Discord/Slack** - Team notifications
- **IFTTT/Zapier** - Connect to any service

See [docs/NOTIFICATIONS.md](docs/NOTIFICATIONS.md) for setup instructions.

## Usage

### Adding Notes

1. Take photos of pages on your phone
2. Sync to `brain-notes/[category]/[source]/` via Nextcloud or file sync
3. Application automatically detects and processes new files

### Searching

Test search after processing files:
```bash
uv run python test_search.py
```

Programmatic search:
```python
from src.second_brain_ocr.indexer import SearchIndexer
from src.second_brain_ocr.embeddings import EmbeddingGenerator

embedding_gen = EmbeddingGenerator(endpoint, api_key, deployment, api_version)
indexer = SearchIndexer(endpoint, api_key, index_name, embedding_dimension)

query_vector = embedding_gen.generate_embedding("public speaking tips")
results = indexer.search("public speaking tips", query_vector, top=5)
```

## Development

### Setup

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

### Run Locally

```bash
uv run python -m src.second_brain_ocr.main
```

### Quality Checks

```bash
uv run pytest                     # Run tests
uv run pytest --cov              # With coverage
uv run ruff check src tests      # Lint
uv run mypy src                  # Type check
uv run pre-commit run --all-files # All hooks
```

See [local testing guide](LOCAL_TESTING.md) for details.

### CI/CD

GitHub Actions runs on every push:
- Tests (36 tests, 86% coverage)
- Linting (ruff)
- Type checking (mypy)
- Docker build and push to ACR (main branch only)

Setup instructions: [docs/CICD_SETUP.md](docs/CICD_SETUP.md)

Required secrets: `ACR_REGISTRY`, `ACR_USERNAME`, `ACR_PASSWORD`

## Supported Formats

Images: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`
Documents: `.pdf`

## Troubleshooting

**Files reprocessed on restart**
- Mount `/app/data` volume for state persistence

**OCR failing**
- Check Azure Document Intelligence quota and pricing tier
- Verify image quality

**No search results**
- Confirm files indexed successfully in logs
- Verify Azure AI Search index exists

**File watching issues on network drives**
- Application automatically falls back to polling mode
- Adjust `POLLING_INTERVAL` if needed

## Architecture

```
Phone → Nextcloud → File Watcher → Azure Document Intelligence (OCR)
                                  ↓
                            Text Content
                                  ↓
                         Azure OpenAI (Embeddings)
                                  ↓
                         Azure AI Search (Vector Store)
```

## Contributing

Contributions welcome! Ensure tests pass before submitting PRs:
```bash
uv run pytest
uv run ruff check src tests
uv run mypy src
```

Pre-commit hooks run automatically after `uv run pre-commit install`.

## License

MIT
