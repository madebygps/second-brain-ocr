"""Main application entry point for Second Brain OCR."""

import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Config
from .embeddings import EmbeddingGenerator
from .indexer import SearchIndexer
from .notifier import WebhookNotifier
from .ocr import OCRProcessor
from .state import StateManager
from .watcher import FileWatcher, scan_existing_files

# Initialize centralized logging
Config.setup_logging()
logger = Config.get_logger(__name__)


class SecondBrainOCR:
    """Main application orchestrator with comprehensive error handling and monitoring."""

    def __init__(self) -> None:
        """Initialize the application with all components.

        Raises:
            SystemExit: If initialization fails due to configuration or service errors
        """
        self.running = False
        self.watcher: FileWatcher | None = None
        self.start_time: datetime | None = None
        self.files_processed_total = 0
        self.files_failed_total = 0
        self.batches_processed = 0

        # Type hints for components (initialized in try block)
        self.notifier: WebhookNotifier
        self.state_manager: StateManager
        self.ocr_processor: OCRProcessor
        self.embedding_generator: EmbeddingGenerator
        self.indexer: SearchIndexer

        logger.info("=" * 60)
        logger.info("Second Brain OCR - Starting")
        logger.info("Version: 1.0.0")
        logger.info("Python: %s", sys.version.split()[0])
        logger.info("=" * 60)

        try:
            # Initialize webhook notifier
            self.notifier = self._initialize_notifier()

            # Ensure directories exist
            Config.ensure_directories()

            # Validate configuration
            errors = Config.validate()
            if errors:
                logger.error("Configuration errors:")
                for error in errors:
                    logger.error("  - %s", error)
                raise SystemExit(1)

            # Initialize state manager
            self.state_manager = self._initialize_state_manager()

            # Initialize OCR processor
            self.ocr_processor = self._initialize_ocr_processor()

            # Initialize embedding generator
            self.embedding_generator = self._initialize_embedding_generator()

            # Initialize search indexer
            embedding_dimension = self._get_embedding_dimension()
            self.indexer = self._initialize_indexer(embedding_dimension)

            # Run health checks
            self._perform_health_checks()

            logger.info("✓ Initialization complete")
            logger.info("=" * 60)

        except SystemExit:
            raise
        except Exception as e:
            logger.exception("Critical error during initialization: %s", e)
            raise SystemExit(1) from e

    def _initialize_notifier(self) -> WebhookNotifier:
        """Initialize webhook notifier with validation.

        Returns:
            Configured WebhookNotifier instance
        """
        try:
            notifier = WebhookNotifier(Config.WEBHOOK_URL)
            if notifier.enabled:
                logger.info("✓ Webhook notifications enabled (%s)", notifier.provider.value)
                # Test webhook if enabled
                if not notifier.test_webhook():
                    logger.warning("⚠ Webhook test failed - continuing without notifications")
            else:
                logger.info("ℹ Webhook notifications disabled")
            return notifier
        except Exception as e:
            logger.warning("Failed to initialize webhook notifier: %s - continuing without notifications", e)
            return WebhookNotifier("")  # Disabled notifier

    def _initialize_state_manager(self) -> StateManager:
        """Initialize state manager with validation.

        Returns:
            Configured StateManager instance
        """
        try:
            state_manager = StateManager(Config.STATE_FILE)
            logger.info("✓ State manager initialized (%d processed files)", state_manager.get_processed_count())
            return state_manager
        except Exception as e:
            logger.error("Failed to initialize state manager: %s", e)
            raise

    def _initialize_ocr_processor(self) -> OCRProcessor:
        """Initialize OCR processor with validation.

        Returns:
            Configured OCRProcessor instance
        """
        try:
            ocr_processor = OCRProcessor(
                endpoint=Config.AZURE_DOC_INTELLIGENCE_ENDPOINT,
                api_key=Config.AZURE_DOC_INTELLIGENCE_KEY,
            )
            logger.info("✓ OCR processor initialized")
            return ocr_processor
        except Exception as e:
            logger.error("Failed to initialize OCR processor: %s", e)
            raise

    def _initialize_embedding_generator(self) -> EmbeddingGenerator:
        """Initialize embedding generator with validation.

        Returns:
            Configured EmbeddingGenerator instance
        """
        try:
            embedding_generator = EmbeddingGenerator(
                endpoint=Config.AZURE_OPENAI_ENDPOINT,
                api_key=Config.AZURE_OPENAI_KEY,
                deployment_name=Config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
                api_version=Config.AZURE_OPENAI_API_VERSION,
            )
            logger.info("✓ Embedding generator initialized")
            return embedding_generator
        except Exception as e:
            logger.error("Failed to initialize embedding generator: %s", e)
            raise

    def _get_embedding_dimension(self) -> int:
        """Determine embedding dimension based on model deployment.

        Returns:
            Embedding dimension size
        """
        deployment = Config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT.lower()
        if "text-embedding-3-large" in deployment:
            dimension = 3072
        elif "text-embedding-3-small" in deployment:
            dimension = 384  # Small model uses 384 dimensions
        else:
            dimension = 1536  # Default for ada-002

        logger.info("✓ Using embedding dimension: %d", dimension)
        return dimension

    def _initialize_indexer(self, embedding_dimension: int) -> SearchIndexer:
        """Initialize search indexer with validation.

        Args:
            embedding_dimension: Size of embedding vectors

        Returns:
            Configured SearchIndexer instance
        """
        try:
            indexer = SearchIndexer(
                endpoint=Config.AZURE_SEARCH_ENDPOINT,
                api_key=Config.AZURE_SEARCH_KEY,
                index_name=Config.AZURE_SEARCH_INDEX_NAME,
                embedding_dimension=embedding_dimension,
            )

            # Create or update index
            indexer.create_or_update_index()
            logger.info("✓ Search index ready: %s", Config.AZURE_SEARCH_INDEX_NAME)
            return indexer

        except Exception as e:
            logger.error("Failed to initialize search indexer: %s", e)
            raise

    def _perform_health_checks(self) -> None:
        """Perform health checks on all components."""
        logger.info("Running health checks...")

        try:
            # Check OCR processor (returns bool)
            try:
                ocr_health = self.ocr_processor.health_check()
                if ocr_health:
                    logger.info("  ✓ OCR processor: healthy")
                else:
                    logger.warning("  ⚠ OCR processor: unhealthy")
            except Exception as e:
                logger.warning("  ⚠ OCR processor health check failed: %s", e)

            # Check embedding generator (returns bool)
            try:
                embedding_health = self.embedding_generator.health_check()
                if embedding_health:
                    logger.info("  ✓ Embedding generator: healthy")
                else:
                    logger.warning("  ⚠ Embedding generator: unhealthy")
            except Exception as e:
                logger.warning("  ⚠ Embedding generator health check failed: %s", e)

            # Check indexer (returns dict)
            try:
                indexer_health = self.indexer.health_check()
                if isinstance(indexer_health, dict) and indexer_health.get("is_healthy"):
                    logger.info("  ✓ Search indexer: healthy")
                else:
                    error_msg = (
                        indexer_health.get("error", "unknown") if isinstance(indexer_health, dict) else "unknown"
                    )
                    logger.warning("  ⚠ Search indexer: unhealthy - %s", error_msg)
            except Exception as e:
                logger.warning("  ⚠ Search indexer health check failed: %s", e)

            # Check state manager (returns dict)
            try:
                state_health = self.state_manager.health_check()
                if isinstance(state_health, dict) and state_health.get("is_healthy"):
                    logger.info("  ✓ State manager: healthy")
                else:
                    error_msg = state_health.get("error", "unknown") if isinstance(state_health, dict) else "unknown"
                    logger.warning("  ⚠ State manager: unhealthy - %s", error_msg)
            except Exception as e:
                logger.warning("  ⚠ State manager health check failed: %s", e)

            # Check notifier (returns dict)
            if self.notifier.enabled:
                try:
                    notifier_health = self.notifier.health_check()
                    if isinstance(notifier_health, dict) and notifier_health.get("is_healthy"):
                        logger.info("  ✓ Webhook notifier: healthy")
                    else:
                        error_msg = (
                            notifier_health.get("error", "unknown") if isinstance(notifier_health, dict) else "unknown"
                        )
                        logger.warning("  ⚠ Webhook notifier: unhealthy - %s", error_msg)
                except Exception as e:
                    logger.warning("  ⚠ Webhook notifier health check failed: %s", e)

        except Exception as e:
            logger.warning("Error during health checks: %s", e)

    def process_file(self, file_path: Path) -> bool:
        """Process a single file through the OCR pipeline.

        Args:
            file_path: Path to the file to process

        Returns:
            True if file was successfully processed, False otherwise
        """
        process_start_time = time.time()

        try:
            # Validate file path
            if not file_path.exists():
                logger.warning("⊘ File not found: %s", file_path)
                return False

            if not file_path.is_file():
                logger.warning("⊘ Not a file: %s", file_path)
                return False

            # Check if already processed
            if self.state_manager.is_processed(str(file_path)):
                logger.info("⊘ Skipping already processed: %s", file_path.name)
                return False

            logger.info("")
            logger.info("→ Processing: %s", file_path.name)

            # Step 1: OCR extraction
            logger.info("  [1/3] Extracting text...")
            ocr_result = self.ocr_processor.extract_text_with_metadata(file_path)

            if not ocr_result or not ocr_result.get("text"):
                logger.warning("  ✗ No text extracted from %s", file_path.name)
                self.files_failed_total += 1
                # Still notify even with 0 words - could indicate a problem
                self.notifier.notify_file_processed(
                    file_path=file_path,
                    word_count=0,
                    title=file_path.stem,
                )
                return False

            extracted_text = str(ocr_result["text"])
            word_count = int(ocr_result.get("word_count", 0))
            logger.info("  ✓ Extracted %d words", word_count)

            # Step 2: Generate embedding
            logger.info("  [2/3] Generating embedding...")
            embedding = self.embedding_generator.generate_embedding(extracted_text)

            if not embedding:
                logger.error("  ✗ Failed to generate embedding for %s", file_path.name)
                self.files_failed_total += 1
                self.notifier.notify_error(file_path, "Failed to generate embedding")
                return False
            logger.info("  ✓ Embedding generated")

            # Step 3: Index document
            logger.info("  [3/3] Indexing document...")
            success = self.indexer.index_document(file_path=file_path, content=extracted_text, embedding=embedding)

            if success:
                # Mark as processed
                self.state_manager.mark_processed(str(file_path))

                process_duration = time.time() - process_start_time
                self.files_processed_total += 1

                logger.info("  ✓ Successfully indexed")
                logger.info("✓ Completed: %s (%d words, %.2fs)", file_path.name, word_count, process_duration)

                # Extract metadata from path
                parts = file_path.parts
                category = parts[-3] if len(parts) >= 3 else ""
                source = parts[-2] if len(parts) >= 2 else ""
                title = " ".join(word.capitalize() for word in source.replace("-", " ").replace("_", " ").split())

                # Send notification
                self.notifier.notify_file_processed(
                    file_path=file_path,
                    word_count=word_count,
                    category=category,
                    source=source,
                    title=title,
                )
                return True
            else:
                logger.error("  ✗ Failed to index %s", file_path.name)
                self.files_failed_total += 1
                self.notifier.notify_error(file_path, "Failed to index document")
                return False

        except KeyboardInterrupt:
            logger.info("⊘ Processing interrupted: %s", file_path.name)
            raise
        except Exception as e:
            logger.exception("✗ Unexpected error processing %s: %s", file_path.name, e)
            self.files_failed_total += 1
            self.notifier.notify_error(file_path, str(e))
            return False

    def process_existing_files(self) -> None:
        """Scan for and process any existing unprocessed files."""
        logger.info("")
        logger.info("Scanning for unprocessed files...")

        try:
            unprocessed_files = scan_existing_files(
                watch_path=Config.WATCH_DIR,
                supported_extensions=Config.SUPPORTED_IMAGE_EXTENSIONS,
                state_manager=self.state_manager,
            )

            if not unprocessed_files:
                logger.info("✓ No unprocessed files found")
                return

            logger.info("Found %d unprocessed file(s)", len(unprocessed_files))
            logger.info("-" * 60)

            batch_start_time = time.time()
            processed_count = 0
            failed_count = 0

            for i, file_path in enumerate(unprocessed_files, 1):
                logger.info("[%d/%d] Processing next file...", i, len(unprocessed_files))

                if not self.running:
                    logger.info("⊘ Batch processing interrupted")
                    break

                success = self.process_file(file_path)
                if success:
                    processed_count += 1
                else:
                    failed_count += 1

            batch_duration = time.time() - batch_start_time
            self.batches_processed += 1

            logger.info("-" * 60)
            logger.info(
                "✓ Batch complete: %d/%d succeeded, %d failed (%.1fs)",
                processed_count,
                len(unprocessed_files),
                failed_count,
                batch_duration,
            )

            if processed_count > 0:
                self.notifier.notify_batch_complete(processed_count, batch_duration)

        except KeyboardInterrupt:
            logger.info("⊘ Batch processing interrupted")
            raise
        except Exception as e:
            logger.exception("Error during batch processing: %s", e)

    def start(self) -> None:
        """Start the application and begin monitoring for files."""
        try:
            self.running = True
            self.start_time = datetime.now(UTC)

            # Process any existing files first
            self.process_existing_files()

            # Start file watcher
            logger.info("")
            logger.info("Starting file watcher...")
            logger.info("  Watching: %s", Config.WATCH_DIR)
            logger.info("  Mode: %s", "polling" if Config.USE_POLLING else "native observer")
            if Config.USE_POLLING:
                logger.info("  Polling interval: %ds", Config.POLLING_INTERVAL)
            logger.info("  Supported extensions: %s", ", ".join(Config.SUPPORTED_IMAGE_EXTENSIONS))

            self.watcher = FileWatcher(
                watch_path=Config.WATCH_DIR,
                callback=self.process_file,
                supported_extensions=Config.SUPPORTED_IMAGE_EXTENSIONS,
                use_polling=Config.USE_POLLING,
            )

            self.watcher.start()

            logger.info("=" * 60)
            logger.info("✓ Ready - Monitoring for new files")
            logger.info("  Press Ctrl+C to stop")
            logger.info("=" * 60)

            # Main loop
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("")
                logger.info("⊘ Interrupt received")

        except Exception as e:
            logger.exception("Critical error in main loop: %s", e)
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the application and cleanup resources."""
        if not self.running:
            return

        logger.info("Shutting down...")
        self.running = False

        try:
            # Stop file watcher
            if self.watcher:
                logger.info("  Stopping file watcher...")
                self.watcher.stop()
                logger.info("  ✓ File watcher stopped")

            # Close notifier
            if self.notifier:
                logger.info("  Closing webhook notifier...")
                self.notifier.close()
                logger.info("  ✓ Notifier closed")

            # Print final statistics
            self._print_final_statistics()

            logger.info("✓ Shutdown complete")

        except Exception as e:
            logger.error("Error during shutdown: %s", e)

    def _print_final_statistics(self) -> None:
        """Print final application statistics."""
        try:
            if self.start_time:
                uptime = (datetime.now(UTC) - self.start_time).total_seconds()
                uptime_str = self._format_duration(uptime)
            else:
                uptime_str = "N/A"

            logger.info("")
            logger.info("=" * 60)
            logger.info("Final Statistics")
            logger.info("=" * 60)
            logger.info("  Uptime: %s", uptime_str)
            logger.info("  Files processed: %d", self.files_processed_total)
            logger.info("  Files failed: %d", self.files_failed_total)
            logger.info("  Batches processed: %d", self.batches_processed)

            # Get component statistics
            if hasattr(self, "state_manager"):
                state_stats = self.state_manager.get_stats()
                logger.info("  Total files tracked: %d", state_stats.get("processed_files_count", 0))

            if hasattr(self, "notifier") and self.notifier.enabled:
                notifier_stats = self.notifier.get_stats()
                logger.info(
                    "  Notifications sent: %d (%.1f%% success rate)",
                    notifier_stats.get("notifications_sent", 0),
                    notifier_stats.get("statistics", {}).get("success_rate", 0.0),
                )

            logger.info("=" * 60)

        except Exception as e:
            logger.error("Error printing final statistics: %s", e)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def get_status(self) -> dict[str, Any]:
        """Get current application status and statistics.

        Returns:
            Dictionary containing application status
        """
        try:
            uptime_seconds = 0.0
            if self.start_time:
                uptime_seconds = (datetime.now(UTC) - self.start_time).total_seconds()

            return {
                "running": self.running,
                "uptime_seconds": uptime_seconds,
                "files_processed_total": self.files_processed_total,
                "files_failed_total": self.files_failed_total,
                "batches_processed": self.batches_processed,
                "state_manager": self.state_manager.get_stats() if hasattr(self, "state_manager") else {},
                "notifier": self.notifier.get_stats() if hasattr(self, "notifier") else {},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error getting application status: %s", e)
            return {"error": str(e), "timestamp": datetime.now(UTC).isoformat()}

    def handle_signal(self, signum: int, frame: Any) -> None:
        """Handle system signals for graceful shutdown.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_names: dict[int, str] = {signal.SIGINT.value: "SIGINT", signal.SIGTERM.value: "SIGTERM"}
        signal_name = signal_names.get(signum, f"Signal {signum}")

        logger.info("")
        logger.info("⊘ Received %s - initiating graceful shutdown...", signal_name)
        self.stop()
        sys.exit(0)


def main() -> None:
    """Main application entry point."""
    app = None
    exit_code = 0

    try:
        app = SecondBrainOCR()

        # Register signal handlers
        signal.signal(signal.SIGINT, app.handle_signal)
        signal.signal(signal.SIGTERM, app.handle_signal)

        # Start application
        app.start()

    except KeyboardInterrupt:
        logger.info("")
        logger.info("⊘ Keyboard interrupt received")
        exit_code = 0
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
    except Exception as e:
        logger.exception("Critical error in main: %s", e)
        exit_code = 1
    finally:
        if app:
            app.stop()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
