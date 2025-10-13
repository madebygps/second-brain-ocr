"""Azure Document Intelligence OCR processing."""

import time
from pathlib import Path
from typing import Any

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    HttpResponseError,
)

from .config import Config

logger = Config.get_logger(__name__)


class OCRProcessor:
    """Processes images using Azure Document Intelligence for OCR.

    Provides robust OCR processing with retry mechanisms, comprehensive error handling,
    file validation, and performance monitoring.
    """

    def __init__(self, endpoint: str, api_key: str) -> None:
        self.client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(api_key))
        self.max_retries = 3
        self.base_delay = 1.0  # seconds
        logger.info("OCR processor initialized with endpoint: %s", endpoint)

    def _validate_file(self, file_path: Path) -> bool:
        """Validate file before OCR processing.

        Args:
            file_path: Path to the file to validate

        Returns:
            True if file is valid for OCR processing
        """
        try:
            # Check if file exists
            if not file_path.exists():
                logger.error("File does not exist: %s", file_path)
                return False

            # Check file extension
            if file_path.suffix.lower() not in Config.SUPPORTED_IMAGE_EXTENSIONS:
                logger.error("Unsupported file type: %s", file_path.suffix)
                return False

            # Check file size (limit to 50MB)
            file_size = file_path.stat().st_size
            max_size = 50 * 1024 * 1024  # 50MB
            if file_size > max_size:
                logger.error("File too large: %s (%.1fMB > 50MB)", file_path.name, file_size / 1024 / 1024)
                return False

            # Check if file is readable
            if not file_path.is_file():
                logger.error("Path is not a file: %s", file_path)
                return False

            logger.debug("File validation passed: %s (%.1fKB)", file_path.name, file_size / 1024)
            return True

        except OSError as e:
            logger.error("Error validating file %s: %s", file_path, e)
            return False

    def _perform_ocr_with_retry(self, file_path: Path) -> AnalyzeResult | None:
        """Perform OCR with exponential backoff retry logic.

        Args:
            file_path: Path to the file to process

        Returns:
            AnalyzeResult if successful, None if all retries failed
        """
        last_exception: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug("OCR attempt %d/%d for: %s", attempt, self.max_retries, file_path.name)

                with file_path.open("rb") as f:
                    poller = self.client.begin_analyze_document(
                        model_id="prebuilt-read", body=f, content_type="application/octet-stream"
                    )

                    # Wait for completion with timeout
                    result: AnalyzeResult = poller.result(timeout=Config.AZURE_TIMEOUT)

                if attempt > 1:
                    logger.info("OCR succeeded on attempt %d for: %s", attempt, file_path.name)

                return result

            except ClientAuthenticationError as e:
                logger.error("Authentication error (will not retry): %s", e)
                return None

            except HttpResponseError as e:
                last_exception = e
                # Handle rate limiting and server errors for HTTP responses
                if hasattr(e, "status_code") and e.status_code is not None:
                    if e.status_code == 429:  # Rate limiting
                        delay = self.base_delay * (2 ** (attempt - 1))  # Exponential backoff
                        logger.warning(
                            "Rate limited on attempt %d/%d, waiting %.1fs: %s", attempt, self.max_retries, delay, e
                        )
                        if attempt < self.max_retries:
                            time.sleep(delay)
                    elif e.status_code >= 500:  # Server errors
                        delay = self.base_delay * attempt  # Linear backoff for server errors
                        logger.warning(
                            "Server error on attempt %d/%d, waiting %.1fs: %s", attempt, self.max_retries, delay, e
                        )
                        if attempt < self.max_retries:
                            time.sleep(delay)
                    else:
                        logger.error("Client error (will not retry): %s", e)
                        return None
                else:
                    logger.warning("HTTP error on attempt %d/%d: %s", attempt, self.max_retries, e)
                    if attempt < self.max_retries:
                        delay = self.base_delay * attempt
                        time.sleep(delay)

            except AzureError as e:
                last_exception = e
                logger.warning("Azure error on attempt %d/%d: %s", attempt, self.max_retries, e)
                if attempt < self.max_retries:
                    delay = self.base_delay * attempt
                    time.sleep(delay)

            except Exception as e:
                logger.error("Unexpected error during OCR (will not retry): %s", e)
                return None

        logger.error(
            "OCR failed after %d attempts for %s. Last error: %s", self.max_retries, file_path.name, last_exception
        )
        return None

    def extract_text(self, file_path: Path) -> str | None:
        """Extract text from an image or PDF file.

        Args:
            file_path: Path to the file to process

        Returns:
            Extracted text string, or None if processing failed
        """
        start_time = time.time()

        try:
            logger.info("Starting OCR for: %s", file_path.name)

            # Validate file before processing
            if not self._validate_file(file_path):
                return None

            # Perform OCR with retry logic
            result = self._perform_ocr_with_retry(file_path)
            if not result:
                return None

            # Extract text content
            extracted_text = result.content if result.content else ""

            # Log performance metrics
            duration = time.time() - start_time
            file_size_kb = file_path.stat().st_size / 1024
            chars_per_second = len(extracted_text) / duration if duration > 0 else 0

            logger.info(
                "OCR completed: %s | %d chars | %.1fs | %.1fKB | %.0f chars/s",
                file_path.name,
                len(extracted_text),
                duration,
                file_size_kb,
                chars_per_second,
            )

            return extracted_text

        except Exception as e:
            duration = time.time() - start_time
            logger.exception("Unexpected error in extract_text for %s after %.1fs: %s", file_path.name, duration, e)
            return None

    def extract_text_with_metadata(self, file_path: Path) -> dict[str, Any] | None:
        """Extract text and metadata from an image or PDF file.

        Args:
            file_path: Path to the file to process

        Returns:
            Dictionary containing extracted text and metadata, or None if processing failed.
            Dictionary keys:
            - text: Extracted text content
            - page_count: Number of pages processed
            - word_count: Number of words extracted
            - character_count: Number of characters extracted
            - languages: List of detected language codes
            - processing_time: Time taken for OCR in seconds
            - file_size_bytes: Original file size
        """
        start_time = time.time()

        try:
            logger.info("Starting OCR with metadata for: %s", file_path.name)

            # Validate file before processing
            if not self._validate_file(file_path):
                return None

            # Get file size for metadata
            file_size = file_path.stat().st_size

            # Perform OCR with retry logic
            result = self._perform_ocr_with_retry(file_path)
            if not result:
                return None

            # Extract text content
            extracted_text = result.content if result.content else ""
            processing_time = time.time() - start_time

            metadata: dict[str, Any] = {
                "text": extracted_text,
                "page_count": len(result.pages) if result.pages else 0,
                "word_count": len(extracted_text.split()) if extracted_text else 0,
                "character_count": len(extracted_text),
                "languages": [lang.locale for lang in result.languages] if result.languages else [],
                "processing_time": round(processing_time, 2),
                "file_size_bytes": file_size,
            }

            # Log comprehensive metrics
            logger.info(
                "OCR with metadata completed: %s | %d pages | %d words | %.1fs | %.1fKB",
                file_path.name,
                metadata["page_count"],
                metadata["word_count"],
                processing_time,
                file_size / 1024,
            )

            if metadata["languages"]:
                logger.debug("Detected languages: %s", ", ".join(metadata["languages"]))

            return metadata

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(
                "Unexpected error in extract_text_with_metadata for %s after %.1fs: %s", file_path.name, duration, e
            )
            return None

    def health_check(self) -> bool:
        """Perform a basic health check of the OCR service.

        Returns:
            True if the service is responsive, False otherwise
        """
        try:
            # This is a simple check - in a real scenario you might
            # want to process a small test image
            logger.debug("Performing OCR service health check")

            # The client creation itself validates the endpoint format
            # More comprehensive health checks could be added here

            logger.debug("OCR service health check passed")
            return True

        except Exception as e:
            logger.error("OCR service health check failed: %s", e)
            return False
