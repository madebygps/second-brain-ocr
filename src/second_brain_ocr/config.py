"""Configuration management and centralized logging for Second Brain OCR."""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _get_int_in_range(env_name: str, default: int, min_val: int, max_val: int) -> int:
    """Get integer from environment with range validation."""
    try:
        value = int(os.getenv(env_name, str(default)))
        if not min_val <= value <= max_val:
            logger.warning(
                "Invalid %s: %d. Using default %d (valid range: %d-%d)", env_name, value, default, min_val, max_val
            )
            return default
        return value
    except (ValueError, TypeError):
        logger.warning("Invalid %s format. Using default %d", env_name, default)
        return default


class Config:
    """Application configuration loaded from environment variables."""

    WATCH_DIR: Path = Path(os.getenv("WATCH_DIR", "/brain-notes"))
    USE_POLLING: bool = os.getenv("USE_POLLING", "true").lower() == "true"
    POLLING_INTERVAL: int = _get_int_in_range("POLLING_INTERVAL", 180, 30, 3600)

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
    BATCH_SIZE: int = _get_int_in_range("BATCH_SIZE", 10, 1, 50)

    STATE_FILE: Path = Path(os.getenv("STATE_FILE", "/app/data/processed_files.json"))

    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")

    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    LOG_DATE_FORMAT: str = os.getenv("LOG_DATE_FORMAT", "%Y-%m-%d %H:%M:%S")
    LOG_TO_FILE: bool = os.getenv("LOG_TO_FILE", "false").lower() == "true"
    LOG_FILE_PATH: Path = Path(os.getenv("LOG_FILE_PATH", "/app/data/second-brain-ocr.log"))
    LOG_FILE_MAX_SIZE: int = _get_int_in_range("LOG_FILE_MAX_SIZE", 10, 1, 100)  # MB
    LOG_FILE_BACKUP_COUNT: int = _get_int_in_range("LOG_FILE_BACKUP_COUNT", 3, 1, 10)

    # Azure SDK Logging
    AZURE_LOG_LEVEL: str = os.getenv("AZURE_LOG_LEVEL", "WARNING").upper()

    # Timeout Configuration
    HTTP_TIMEOUT: int = _get_int_in_range("HTTP_TIMEOUT", 10, 5, 60)
    AZURE_TIMEOUT: int = _get_int_in_range("AZURE_TIMEOUT", 30, 10, 120)

    # Text Processing Configuration
    TEXT_CHUNK_MAX_TOKENS: int = _get_int_in_range("TEXT_CHUNK_MAX_TOKENS", 8000, 1000, 32000)
    TEXT_CHUNK_OVERLAP: int = _get_int_in_range("TEXT_CHUNK_OVERLAP", 200, 50, 1000)

    # Index Storage Optimization
    MAX_CONTENT_LENGTH: int = _get_int_in_range("MAX_CONTENT_LENGTH", 1000, 100, 10000)  # chars to store in index

    # File Watcher Configuration
    FILE_DETECTION_DELAY: float = float(os.getenv("FILE_DETECTION_DELAY", "1.0"))

    @classmethod
    def _validate_url(cls, url: str, name: str) -> str:
        """Validate URL format and return error message if invalid."""
        if not url:
            return f"{name} is required"

        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return f"{name} must be a valid URL (got: {url[:50]}...)"
            if parsed.scheme not in ["https", "http"]:
                return f"{name} must use HTTP/HTTPS protocol (got: {parsed.scheme})"
        except Exception:
            return f"{name} has invalid URL format (got: {url[:50]}...)"

        return ""

    @classmethod
    def _validate_path(cls, path: Path, name: str, should_exist: bool = False) -> str:
        """Validate path and return error message if invalid."""
        try:
            if should_exist and not path.exists():
                return f"{name} directory does not exist: {path}"
            # Check if parent directory is writable for files that will be created
            if not should_exist and not path.parent.exists():
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    return f"Cannot create parent directory for {name}: {e}"
        except OSError as e:
            return f"Invalid path for {name}: {e}"

        return ""

    @classmethod
    def validate(cls) -> list[str]:
        """Validate all configuration values with detailed error messages."""
        errors = []

        # Required Azure service endpoints and keys
        azure_configs = [
            (cls.AZURE_DOC_INTELLIGENCE_ENDPOINT, "AZURE_DOC_INTELLIGENCE_ENDPOINT"),
            (cls.AZURE_OPENAI_ENDPOINT, "AZURE_OPENAI_ENDPOINT"),
            (cls.AZURE_SEARCH_ENDPOINT, "AZURE_SEARCH_ENDPOINT"),
        ]

        for url, name in azure_configs:
            error = cls._validate_url(url, name)
            if error:
                errors.append(error)

        # Required API keys
        required_keys = {
            "AZURE_DOC_INTELLIGENCE_KEY": cls.AZURE_DOC_INTELLIGENCE_KEY,
            "AZURE_OPENAI_KEY": cls.AZURE_OPENAI_KEY,
            "AZURE_SEARCH_KEY": cls.AZURE_SEARCH_KEY,
        }

        for name, value in required_keys.items():
            if not value or not value.strip():
                errors.append(f"{name} is required and cannot be empty")

        # Validate webhook URL if provided
        if cls.WEBHOOK_URL:
            error = cls._validate_url(cls.WEBHOOK_URL, "WEBHOOK_URL")
            if error:
                errors.append(error)

        # Validate paths
        path_error = cls._validate_path(cls.STATE_FILE.parent, "STATE_FILE parent directory")
        if path_error:
            errors.append(path_error)

        # Validate embedding deployment name
        valid_deployments = [
            "text-embedding-ada-002",  # 1536 dims
            "text-embedding-3-small",  # 384 dims (recommended for free tier)
            "text-embedding-3-large",  # 3072 dims
        ]
        if cls.AZURE_OPENAI_EMBEDDING_DEPLOYMENT not in valid_deployments:
            logger.warning(
                "Unknown embedding deployment: %s. Supported: %s",
                cls.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
                ", ".join(valid_deployments),
            )

        return errors

    @classmethod
    def setup_logging(cls) -> None:
        """Configure centralized logging for the entire application."""
        # Convert string log level to logging constant
        numeric_level = getattr(logging, cls.LOG_LEVEL, logging.INFO)
        azure_numeric_level = getattr(logging, cls.AZURE_LOG_LEVEL, logging.WARNING)

        # Clear any existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        # Create formatter
        formatter = logging.Formatter(fmt=cls.LOG_FORMAT, datefmt=cls.LOG_DATE_FORMAT)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # File handler (if enabled)
        if cls.LOG_TO_FILE:
            try:
                cls.LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.handlers.RotatingFileHandler(
                    cls.LOG_FILE_PATH,
                    maxBytes=cls.LOG_FILE_MAX_SIZE * 1024 * 1024,  # Convert MB to bytes
                    backupCount=cls.LOG_FILE_BACKUP_COUNT,
                )
                file_handler.setLevel(numeric_level)
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
            except OSError as e:
                # Fallback to console only if file logging fails
                console_handler.setLevel(logging.WARNING)
                root_logger.error("Failed to setup file logging: %s. Using console only.", e)

        # Set root logger level
        root_logger.setLevel(numeric_level)

        # Configure Azure SDK logging
        logging.getLogger("azure").setLevel(azure_numeric_level)
        logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(azure_numeric_level)

        # Log the configuration
        logger = logging.getLogger(__name__)
        logger.info("Logging configured: level=%s, file_logging=%s", cls.LOG_LEVEL, cls.LOG_TO_FILE)
        if cls.LOG_TO_FILE:
            logger.info(
                "Log file: %s (max_size=%dMB, backups=%d)",
                cls.LOG_FILE_PATH,
                cls.LOG_FILE_MAX_SIZE,
                cls.LOG_FILE_BACKUP_COUNT,
            )

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get a logger instance with consistent configuration.

        Args:
            name: Logger name, typically __name__ from the calling module

        Returns:
            Configured logger instance
        """
        return logging.getLogger(name)

    @classmethod
    def ensure_directories(cls) -> None:
        """Create necessary directories if they don't exist."""
        directories = [cls.WATCH_DIR, cls.STATE_FILE.parent]

        # Add log file directory if file logging is enabled
        if cls.LOG_TO_FILE:
            directories.append(cls.LOG_FILE_PATH.parent)

        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                logger.debug("Ensured directory exists: %s", directory)
            except OSError as e:
                logger.error("Failed to create directory %s: %s", directory, e)
                raise
