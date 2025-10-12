# Second Brain OCR

![Tests](https://github.com/your-username/second-brain-ocr/workflows/CI%2FCD%20Pipeline/badge.svg)
![Coverage](https://codecov.io/gh/your-username/second-brain-ocr/branch/main/graph/badge.svg)

Automated OCR and semantic search for your second brain notes. Captures text from images, generates embeddings, and enables intelligent search across your knowledge base.

## Features

- **Automated Processing**: Watches directories for new images, extracts text via OCR, generates embeddings, and indexes for search
- **Semantic Search**: Query your notes using natural language with vector similarity search
- **State Management**: Tracks processed files to avoid reprocessing
- **Docker-First**: Containerized for deployment on Synology NAS, Portainer, or any Docker host
- **Nextcloud Integration**: Works seamlessly with Nextcloud-synced photo uploads

## Quick Start

### Prerequisites

Create these Azure resources ([detailed setup guide](docs/AZURE_SETUP.md)):
- Azure Document Intelligence
- Azure OpenAI (with text-embedding deployment)
- Azure AI Search (free tier works for ~2,500 documents)

### Docker Deployment

1. **Clone and configure:**
   ```bash
   git clone https://github.com/your-username/second-brain-ocr.git
   cd second-brain-ocr
   cp .env.example .env
   # Edit .env with your Azure credentials
   ```

2. **Update volume paths in `docker-compose.yml`:**
   ```yaml
   volumes:
     - /path/to/your/brain-notes:/brain-notes:ro
     - ./data:/app/data
   ```

3. **Start the service:**
   ```bash
   docker-compose up -d
   docker-compose logs -f
   ```

### Directory Structure

Organize your notes like this:
```
brain-notes/
├── books/
│   └── win-every-argument/
│       ├── page1.jpg
│       └── page2.jpg
├── articles/
│   └── productivity-article/
└── essays/
    └── philosophy-notes/
```

The app automatically extracts:
- **Category**: `books`, `articles`, `essays`
- **Source**: Folder name (e.g., `win-every-argument`)
- **Title**: Formatted from folder name (e.g., "Win Every Argument")

## Development

### Local Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linting
uv run ruff check src tests

# Type checking
uv run mypy src

# Start application
uv run python -m second_brain_ocr.main
```

### Testing Search

```bash
# After processing some images, test search:
python test_search.py
```

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `WATCH_DIR` | Directory to monitor | `/brain-notes` |
| `POLLING_INTERVAL` | Fallback polling interval (seconds) | `180` |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | OCR service endpoint | Required |
| `AZURE_DOC_INTELLIGENCE_KEY` | OCR service key | Required |
| `AZURE_OPENAI_ENDPOINT` | OpenAI service endpoint | Required |
| `AZURE_OPENAI_KEY` | OpenAI service key | Required |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding model name | `text-embedding-ada-002` |
| `AZURE_SEARCH_ENDPOINT` | Search service endpoint | Required |
| `AZURE_SEARCH_KEY` | Search service key | Required |
| `STATE_FILE` | Processed files tracker | `/app/data/processed_files.json` |

See `.env.example` for complete configuration template.

## Deployment Options

### Synology NAS with Portainer

1. Build and push to Azure Container Registry:
   ```bash
   ./build-acr.sh yourregistry.azurecr.io
   ```

2. In Portainer:
   - Add ACR as registry (Azure Portal > ACR > Access keys)
   - Create stack from `docker-compose.acr.yml`
   - Set environment variables
   - Update Nextcloud volume path
   - Deploy

See [ACR_DEPLOYMENT.md](ACR_DEPLOYMENT.md) for detailed instructions.

### Other Registries

```bash
# Docker Hub
docker build -t username/second-brain-ocr:latest .
docker push username/second-brain-ocr:latest

# GitHub Container Registry
docker build -t ghcr.io/username/second-brain-ocr:latest .
docker push ghcr.io/username/second-brain-ocr:latest
```

## Usage

### Adding Notes

1. Take photos of book pages/articles on your phone
2. Let Nextcloud sync to `brain-notes/[category]/[source]/`
3. Watch the logs as files are automatically processed

### Searching

Use the provided search script:
```bash
python test_search.py
# Enter query: "what are the best public speaking tips?"
```

Or integrate programmatically:
```python
from second_brain_ocr.indexer import SearchIndexer
from second_brain_ocr.embeddings import EmbeddingGenerator

embedding_gen = EmbeddingGenerator(...)
indexer = SearchIndexer(...)

query = "public speaking tips"
query_vector = embedding_gen.generate_embedding(query)
results = indexer.search(query, query_vector, top=5)
```

## CI/CD

The project includes GitHub Actions workflows for:
- **Tests**: Pytest with coverage reporting
- **Linting**: Ruff for code quality
- **Type Checking**: mypy for type safety
- **Docker Build**: Automated ACR image builds on push to main

Configure secrets in GitHub:
- `ACR_REGISTRY`
- `ACR_USERNAME`
- `ACR_PASSWORD`
- `CODECOV_TOKEN` (optional)

## Supported Formats

- Images: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`
- Documents: `.pdf`

## Troubleshooting

**Files reprocessed on restart?**
- Ensure `/app/data` volume is mounted for state persistence

**OCR failing?**
- Check Azure Document Intelligence quota
- Verify image quality and readability

**Search returns no results?**
- Confirm files were successfully indexed (check logs)
- Verify Azure AI Search index exists
- Try test_search.py for diagnostics

**Network drive monitoring issues?**
- App automatically falls back to polling mode
- Adjust `POLLING_INTERVAL` if needed

## Architecture

```
┌─────────────┐
│ Phone Photo │
└──────┬──────┘
       │ Nextcloud Sync
       ▼
┌────────────────┐
│  File Watcher  │
└───────┬────────┘
        │
        ▼
┌──────────────────┐    ┌────────────────┐
│ Azure Doc Intel  │───▶│  Text Content  │
│      (OCR)       │    └───────┬────────┘
└──────────────────┘            │
                                ▼
                      ┌──────────────────┐
                      │   Azure OpenAI   │
                      │   (Embeddings)   │
                      └────────┬─────────┘
                               │
                               ▼
                    ┌────────────────────┐
                    │ Azure AI Search    │
                    │  (Vector Store)    │
                    └────────────────────┘
```

## License

MIT

## Contributing

Contributions welcome! Run tests before submitting PRs:
```bash
uv run pytest
uv run ruff check src tests
```
