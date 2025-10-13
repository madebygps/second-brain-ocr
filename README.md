# Second Brain OCR

![CI/CD Pipeline](https://github.com/madebygps/second-brain-ocr/actions/workflows/ci-cd.yml/badge.svg)

Automated OCR and semantic search for second brain notes. Watches directories, extracts text with Azure Document Intelligence, generates embeddings with Azure OpenAI, and indexes in Azure AI Search.

**Features:** Polling file detection • OCR for images/PDFs • Vector embeddings • State management • Docker deployment • CI/CD • Webhook notifications

**Prerequisites:** Azure Document Intelligence, Azure OpenAI (embedding model), Azure AI Search (free tier: ~2,500 docs)

## Quick Start

```bash
git clone https://github.com/madebygps/second-brain-ocr.git
cd second-brain-ocr
cp .env.example .env  # Add Azure credentials
# Edit docker-compose.yml volume paths
docker-compose up -d
```

**Portainer:** Images auto-built to ACR on commits. See [CI/CD guide](docs/CICD_SETUP.md) and [ACR deployment](ACR_DEPLOYMENT.md).

## Directory Structure

```
brain-notes/
├── books/atomic-habits/page1.jpg
├── articles/productivity-tips/
└── essays/philosophy-notes/
```

**Metadata:** Category (top folder) • Source (subfolder) • Title (formatted source)

## Configuration

**File Detection:** Polling mode (default, every 180s) works with Nextcloud/network shares. Event-based mode (`USE_POLLING=false`) for instant detection with direct file access only.

**Key Variables:** `WATCH_DIR`, `USE_POLLING`, `POLLING_INTERVAL`, Azure endpoints/keys. See `.env.example`.

**Notifications:** Configure `WEBHOOK_URL` for ntfy.sh, Discord, Slack, IFTTT. See [NOTIFICATIONS.md](docs/NOTIFICATIONS.md).

## Usage

**Add notes:** Photo → Sync to `brain-notes/[category]/[source]/` → Auto-processed

**Search:** `uv run python scripts/test_search.py` or programmatically via `SearchIndexer`

## Development

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && uv sync
uv run python -m src.second_brain_ocr.main  # Run locally
uv run pytest --cov                         # Test
uv run ruff check src tests                 # Lint
uv run pre-commit run --all-files           # All checks
```

**CI/CD:** Auto-tests, linting, Docker build on push. See [CICD_SETUP.md](docs/CICD_SETUP.md).

**Formats:** `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.pdf`

## Utilities

```bash
uv run python scripts/check_index_stats.py  # Index stats
uv run python scripts/clear_index.py        # Clear index
uv run python scripts/test_search.py        # Test search
```

## Troubleshooting

- **Files reprocessed:** Mount `/app/data` volume
- **OCR failing:** Check Azure quota/tier, image quality
- **No results:** Check logs, verify index exists
- **Not detecting:** Polling checks every 180s by default

## Architecture

Phone → Nextcloud → Watcher → Azure Doc Intelligence (OCR) → Azure OpenAI (Embeddings) → Azure AI Search (Vector Store)

## License

MIT
