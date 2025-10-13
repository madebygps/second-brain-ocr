# Second Brain OCR - Development Guide

**Status:** Production-ready Python 3.13 app with Azure services (Document Intelligence, OpenAI, AI Search)

**Tech Stack:** `uv` package manager • watchdog • Docker • CI/CD (GitHub Actions + ACR)

**Core Principles:** Centralized config/logging • Error handling with retries • Health checks • Minimal testing (7 essential tests)

## Architecture Rules

**1. Centralized Config:** Use `Config.VARIABLE` from `config.py`, never `os.getenv()` directly

**2. Centralized Logging:** Use `Config.get_logger(__name__)`, never `logging.getLogger()`

**3. Module Pattern:**
```python
"""Module docstring."""
from pathlib import Path
from .config import Config

logger = Config.get_logger(__name__)

class Component:
    def __init__(self, endpoint: str, api_key: str) -> None:
        # Implementation
```

## Structure

```
src/second_brain_ocr/
├── config.py       # Centralized config & logging
├── main.py         # Orchestrator
├── ocr.py          # Azure Document Intelligence
├── embeddings.py   # Azure OpenAI
├── indexer.py      # Azure AI Search
├── state.py        # Processed files tracker
├── watcher.py      # File monitoring
└── notifier.py     # Webhooks

tests/              # 7 essential tests
scripts/            # Utility scripts
```

## Configuration

**Key vars:** Azure endpoints/keys, `WATCH_DIR`, `USE_POLLING`, `POLLING_INTERVAL`, `BATCH_SIZE`, log settings

**Adding config:**
1. Add to `Config` class with validation helper
2. Update `.env.example`
3. Add validation if needed

## Testing

**Strategy:** 7 essential tests (1 config, 4 integration, 2 state) - personal project, no extensive unit tests for Azure SDKs

**Run:** `uv run pytest --cov` or `uv run pytest tests/test_config.py -v`

## Error Handling

**Pattern:** Try-except with specific exceptions, log errors, return False/None, notify on critical errors

**Azure:** Handle rate limits (429), retries with backoff, catch `ServiceRequestError` and `AzureError`

## Performance

- Batch processing via `BATCH_SIZE`
- State management prevents reprocessing
- Exponential backoff for rate limits
- Stream large files, use generators
- Synchronous by design (simplicity over speed)

## Docker

**Volumes:** `/brain-notes` (read-only input), `/app/data` (persistent state)

**Base:** Python 3.13-slim with `uv` package manager

## Logging

**Levels:** DEBUG (execution), INFO (operations), WARNING (issues), ERROR (failures), CRITICAL (app-level)

**Webhooks:** Processing complete, batch complete, errors, health status

## Security

- Never log API keys
- Validate file extensions and sizes
- Prevent path traversal (`..` in paths)
- Use environment variables for secrets

## Code Style

**Type hints:** Modern syntax (`list[Path]` not `List[Path]`)

**Imports:** Standard lib → Third-party → Local, alphabetical within groups

**Docs:** Docstrings with one-line summary, Args, Returns, Raises

## Commands

```bash
uv sync                                    # Install deps
uv run pytest --cov                       # Test
uv run ruff check src tests               # Lint
uv run ruff format src tests              # Format
uv run python -m src.second_brain_ocr.main # Run
uv add package-name                       # Add dep
uv add --dev package-name                 # Add dev dep
uv sync --upgrade                         # Update deps
```

## CI/CD

**pre-commit.ci:** Auto-fixes PRs (trailing whitespace, formatting, linting) • Weekly dependency updates • Comment `pre-commit.ci run` to re-run

**GitHub Actions:** Tests → Docker build → ACR push (main only)

**Flow:** PR → pre-commit.ci fixes → Tests pass → Merge → Build → Deploy

## Workflow

**Setup:** `curl -LsSf https://astral.sh/uv/install.sh | sh && uv sync && uv run pre-commit install`

**Changes:** Branch → Edit → Push → pre-commit.ci auto-fixes → Review → Merge

**Checklist:** Uses Config • Has tests • Error handling • No hardcoded values • Clear commits

## Key Rules

1. Config through `Config` class only
2. Logging through `Config.get_logger()` only
3. Always use `uv run` for Python commands
4. Graceful error handling with retries
5. Minimal testing (7 tests) - personal project
6. Health checks via `health_check()` method
7. Document the "why"
8. Correctness over performance
