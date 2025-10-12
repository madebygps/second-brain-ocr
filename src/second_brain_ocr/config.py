"""Configuration management for Second Brain OCR."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    WATCH_DIR: Path = Path(os.getenv("WATCH_DIR", "/brain-notes"))
    POLLING_INTERVAL: int = int(os.getenv("POLLING_INTERVAL", "180"))

    AZURE_DOC_INTELLIGENCE_ENDPOINT: str = os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "")
    AZURE_DOC_INTELLIGENCE_KEY: str = os.getenv("AZURE_DOC_INTELLIGENCE_KEY", "")

    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_KEY: str = os.getenv("AZURE_OPENAI_KEY", "")
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

    AZURE_SEARCH_ENDPOINT: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    AZURE_SEARCH_KEY: str = os.getenv("AZURE_SEARCH_KEY", "")
    AZURE_SEARCH_INDEX_NAME: str = os.getenv("AZURE_SEARCH_INDEX_NAME", "second-brain-notes")

    SUPPORTED_IMAGE_EXTENSIONS: tuple[str, ...] = (
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tiff",
        ".pdf",
    )
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "10"))

    STATE_FILE: Path = Path(os.getenv("STATE_FILE", "/app/data/processed_files.json"))

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration values."""
        required_fields = {
            "AZURE_DOC_INTELLIGENCE_ENDPOINT": cls.AZURE_DOC_INTELLIGENCE_ENDPOINT,
            "AZURE_DOC_INTELLIGENCE_KEY": cls.AZURE_DOC_INTELLIGENCE_KEY,
            "AZURE_OPENAI_ENDPOINT": cls.AZURE_OPENAI_ENDPOINT,
            "AZURE_OPENAI_KEY": cls.AZURE_OPENAI_KEY,
            "AZURE_SEARCH_ENDPOINT": cls.AZURE_SEARCH_ENDPOINT,
            "AZURE_SEARCH_KEY": cls.AZURE_SEARCH_KEY,
        }

        return [f"{name} is required" for name, value in required_fields.items() if not value]
