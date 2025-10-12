"""Main application entry point for Second Brain OCR."""

import logging
import signal
import sys
import time
from pathlib import Path

from .config import Config
from .embeddings import EmbeddingGenerator
from .indexer import SearchIndexer
from .notifier import WebhookNotifier
from .ocr import OCRProcessor
from .state import StateManager
from .watcher import FileWatcher, scan_existing_files

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


class SecondBrainOCR:
    """Main application orchestrator."""

    def __init__(self) -> None:
        self.running = False
        self.watcher: FileWatcher | None = None

        logger.info("=" * 60)
        logger.info("Second Brain OCR - Starting")
        logger.info("=" * 60)

        self.notifier = WebhookNotifier(Config.WEBHOOK_URL)
        if self.notifier.enabled:
            logger.info("✓ Webhook notifications enabled")

        errors = Config.validate()
        if errors:
            logger.error("Configuration errors:")
            for error in errors:
                logger.error("  - %s", error)
            sys.exit(1)

        self.state_manager = StateManager(Config.STATE_FILE)

        self.ocr_processor = OCRProcessor(
            endpoint=Config.AZURE_DOC_INTELLIGENCE_ENDPOINT, api_key=Config.AZURE_DOC_INTELLIGENCE_KEY
        )

        self.embedding_generator = EmbeddingGenerator(
            endpoint=Config.AZURE_OPENAI_ENDPOINT,
            api_key=Config.AZURE_OPENAI_KEY,
            deployment_name=Config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            api_version=Config.AZURE_OPENAI_API_VERSION,
        )

        embedding_dimension = 1536
        if "text-embedding-3-large" in Config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT:
            embedding_dimension = 3072
        elif "text-embedding-3-small" in Config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT:
            embedding_dimension = 1536

        logger.info("✓ Using embedding dimension: %d", embedding_dimension)

        self.indexer = SearchIndexer(
            endpoint=Config.AZURE_SEARCH_ENDPOINT,
            api_key=Config.AZURE_SEARCH_KEY,
            index_name=Config.AZURE_SEARCH_INDEX_NAME,
            embedding_dimension=embedding_dimension,
        )

        try:
            self.indexer.create_or_update_index()
            logger.info("✓ Search index ready: %s", Config.AZURE_SEARCH_INDEX_NAME)
        except (ValueError, AttributeError) as e:
            logger.error("✗ Failed to initialize search index: %s", e)
            sys.exit(1)

        logger.info("✓ Initialization complete")
        logger.info("=" * 60)

    def process_file(self, file_path: Path) -> None:
        try:
            if self.state_manager.is_processed(str(file_path)):
                logger.info("⊘ Skipping already processed: %s", file_path.name)
                return

            logger.info("")
            logger.info("→ Processing: %s", file_path.name)

            logger.info("  [1/3] Extracting text...")
            ocr_result = self.ocr_processor.extract_text_with_metadata(file_path)

            if not ocr_result or not ocr_result.get("text"):
                logger.warning("  ✗ No text extracted")
                return

            extracted_text = str(ocr_result["text"])
            word_count = int(ocr_result.get("word_count", 0))
            logger.info("  ✓ Extracted %d words", word_count)

            logger.info("  [2/3] Generating embedding...")
            embedding = self.embedding_generator.generate_embedding(extracted_text)

            if not embedding:
                logger.error("  ✗ Failed to generate embedding")
                return
            logger.info("  ✓ Embedding generated")

            logger.info("  [3/3] Indexing document...")
            success = self.indexer.index_document(file_path=file_path, content=extracted_text, embedding=embedding)

            if success:
                self.state_manager.mark_processed(str(file_path))
                logger.info("  ✓ Successfully indexed")
                logger.info("✓ Completed: %s (%d words)", file_path.name, word_count)

                parts = file_path.parts
                category = parts[-3] if len(parts) >= 3 else ""
                source = parts[-2] if len(parts) >= 2 else ""
                title = " ".join(word.capitalize() for word in source.replace("-", " ").replace("_", " ").split())

                self.notifier.notify_file_processed(
                    file_path=file_path,
                    word_count=word_count,
                    category=category,
                    source=source,
                    title=title,
                )
            else:
                logger.error("  ✗ Failed to index")
                logger.error("✗ Failed: %s", file_path.name)

        except (OSError, ValueError, AttributeError) as e:
            logger.error("✗ Error processing %s: %s", file_path.name, e)
            self.notifier.notify_error(file_path, str(e))

    def process_existing_files(self) -> None:
        logger.info("")
        logger.info("Scanning for unprocessed files...")

        unprocessed_files = scan_existing_files(
            watch_path=Config.WATCH_DIR,
            supported_extensions=Config.SUPPORTED_IMAGE_EXTENSIONS,
            state_manager=self.state_manager,
        )

        if unprocessed_files:
            logger.info("Found %d unprocessed file(s)", len(unprocessed_files))
            logger.info("-" * 60)
            start_time = time.time()
            processed_count = 0

            for file_path in unprocessed_files:
                self.process_file(file_path)
                if self.state_manager.is_processed(str(file_path)):
                    processed_count += 1

            elapsed_time = time.time() - start_time
            logger.info("-" * 60)
            if processed_count > 0:
                logger.info("✓ Batch complete: %d file(s) in %.1fs", processed_count, elapsed_time)
                self.notifier.notify_batch_complete(processed_count, elapsed_time)
            else:
                logger.info("✗ No files successfully processed")
        else:
            logger.info("✓ No unprocessed files found")

    def start(self) -> None:
        self.running = True

        self.process_existing_files()

        logger.info("")
        logger.info("Starting file watcher...")
        logger.info("Watching: %s", Config.WATCH_DIR)
        logger.info("Polling interval: %ds", Config.POLLING_INTERVAL)
        self.watcher = FileWatcher(
            watch_path=Config.WATCH_DIR,
            callback=self.process_file,
            supported_extensions=Config.SUPPORTED_IMAGE_EXTENSIONS,
            polling_interval=Config.POLLING_INTERVAL,
        )

        self.watcher.start()

        logger.info("=" * 60)
        logger.info("✓ Ready - Monitoring for new files")
        logger.info("=" * 60)

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("")
            logger.info("Interrupt received")
            self.stop()

    def stop(self) -> None:
        logger.info("Shutting down...")
        self.running = False

        if self.watcher:
            self.watcher.stop()

        logger.info("✓ Shutdown complete")

    def handle_signal(self, signum: int, frame) -> None:
        logger.info("Received signal %d", signum)
        self.stop()
        sys.exit(0)


def main() -> None:
    app = SecondBrainOCR()

    signal.signal(signal.SIGINT, app.handle_signal)
    signal.signal(signal.SIGTERM, app.handle_signal)

    app.start()


if __name__ == "__main__":
    main()
