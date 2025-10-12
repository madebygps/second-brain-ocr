"""Azure Document Intelligence OCR processing."""

import logging
from pathlib import Path
from typing import Any

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AzureKeyCredential

logger = logging.getLogger(__name__)


class OCRProcessor:
    """Processes images using Azure Document Intelligence for OCR."""

    def __init__(self, endpoint: str, api_key: str) -> None:
        self.client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(api_key))

    def extract_text(self, file_path: Path) -> str | None:
        try:
            logger.info("Processing OCR for: %s", file_path)

            with file_path.open("rb") as f:
                poller = self.client.begin_analyze_document(
                    model_id="prebuilt-read", body=f, content_type="application/octet-stream"
                )
                result: AnalyzeResult = poller.result()

            extracted_text = result.content if result.content else ""

            logger.info("Successfully extracted %d characters from %s", len(extracted_text), file_path.name)
            return extracted_text

        except (OSError, ValueError) as e:
            logger.error("Error processing OCR for %s: %s", file_path, e)
            return None

    def extract_text_with_metadata(self, file_path: Path) -> dict[str, Any] | None:
        try:
            logger.info("Processing OCR with metadata for: %s", file_path)

            with file_path.open("rb") as f:
                poller = self.client.begin_analyze_document(
                    model_id="prebuilt-read", body=f, content_type="application/octet-stream"
                )
                result: AnalyzeResult = poller.result()

            extracted_text = result.content if result.content else ""

            metadata: dict[str, Any] = {
                "text": extracted_text,
                "page_count": len(result.pages) if result.pages else 0,
                "word_count": len(extracted_text.split()),
                "character_count": len(extracted_text),
                "languages": [lang.locale for lang in result.languages] if result.languages else [],
            }

            logger.info(
                "Extracted %d pages, %d words from %s",
                metadata["page_count"],
                metadata["word_count"],
                file_path.name,
            )
            return metadata

        except (OSError, ValueError) as e:
            logger.error("Error processing OCR with metadata for %s: %s", file_path, e)
            return None
