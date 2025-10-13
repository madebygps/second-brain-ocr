"""File system watcher with event-based monitoring and polling fallback."""

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingObserver

if TYPE_CHECKING:
    from .state import StateManager

from .config import Config

logger = Config.get_logger(__name__)


class ImageFileHandler(FileSystemEventHandler):
    """Handler for new image file events with robust error handling and validation."""

    def __init__(
        self,
        callback: Callable[[Path], None] | Callable[[Path], bool],
        supported_extensions: tuple[str, ...],
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        """Initialize the file handler with retry configuration.

        Args:
            callback: Function to call when a new file is detected
            supported_extensions: File extensions to monitor
            max_retries: Maximum number of retry attempts for failed callbacks
            base_delay: Base delay in seconds for exponential backoff
        """
        if not self._validate_config(callback, supported_extensions):
            raise ValueError("Invalid file handler configuration")

        self.callback = callback
        self.supported_extensions = supported_extensions
        self.max_retries = max_retries
        self.base_delay = base_delay

        # Performance tracking
        self.files_processed = 0
        self.files_failed = 0
        self.callback_errors = 0
        self._lock = threading.Lock()

        logger.info("ImageFileHandler initialized - extensions: %s, max_retries: %d", supported_extensions, max_retries)

    def _validate_config(
        self, callback: Callable[[Path], None] | Callable[[Path], bool], supported_extensions: tuple[str, ...]
    ) -> bool:
        """Validate handler configuration.

        Args:
            callback: Function to call when a new file is detected
            supported_extensions: File extensions to monitor

        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            # Validate callback
            if not callable(callback):
                logger.error("Invalid callback: must be callable")
                return False

            # Validate extensions
            if not supported_extensions or not isinstance(supported_extensions, tuple):
                logger.error("Invalid supported_extensions: must be a non-empty tuple")
                return False

            if not all(isinstance(ext, str) and ext.startswith(".") for ext in supported_extensions):
                logger.error("Invalid extensions: all must be strings starting with '.'")
                return False

            return True

        except Exception as e:
            logger.error("Error validating file handler configuration: %s", e)
            return False

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events with comprehensive error handling.

        Args:
            event: File system event
        """
        try:
            # Skip directories
            if event.is_directory:
                return

            file_path = Path(str(event.src_path))

            # Basic validation
            if file_path.suffix.lower() not in self.supported_extensions:
                return

            logger.info("New file detected: %s", file_path)

            # Wait for file to be fully written
            detection_delay = getattr(Config, "FILE_DETECTION_DELAY", 2.0)
            if detection_delay > 0:
                time.sleep(detection_delay)

            # Execute callback with retry logic
            success = self._execute_callback_with_retry(file_path)

            if success:
                logger.info("Successfully processed file: %s", file_path.name)
                with self._lock:
                    self.files_processed += 1
            else:
                logger.error("Failed to process file: %s", file_path.name)
                with self._lock:
                    self.files_failed += 1

        except Exception as e:
            logger.error("Unexpected error in file event handler: %s", e)
            with self._lock:
                self.callback_errors += 1

    def _execute_callback_with_retry(self, file_path: Path) -> bool:
        """Execute callback with retry logic.

        Args:
            file_path: Path to process

        Returns:
            True if callback succeeded, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                self.callback(file_path)
                return True

            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    logger.warning(
                        "Callback failed for %s (attempt %d/%d): %s. Retrying in %.1fs...",
                        file_path.name,
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error("All callback attempts failed for %s: %s", file_path.name, e)

        return False

    def get_stats(self) -> dict[str, Any]:
        """Get handler performance statistics.

        Returns:
            Dictionary containing performance metrics
        """
        with self._lock:
            total_files = self.files_processed + self.files_failed
            success_rate = (self.files_processed / max(total_files, 1)) * 100

            return {
                "files_processed": self.files_processed,
                "files_failed": self.files_failed,
                "callback_errors": self.callback_errors,
                "total_files": total_files,
                "success_rate": success_rate,
                "supported_extensions": self.supported_extensions,
                "max_retries": self.max_retries,
                "timestamp": datetime.now(UTC).isoformat(),
            }


class FileWatcher:
    """File watcher with both event-based and polling fallback, comprehensive error handling and monitoring."""

    def __init__(
        self,
        watch_path: Path,
        supported_extensions: tuple[str, ...],
        callback: Callable[[Path], None] | Callable[[Path], bool],
        use_polling: bool = False,
        max_retries: int = 3,
        base_delay: float = 1.0,
        polling_interval: float = 10.0,
    ) -> None:
        """Initialize the file watcher with configuration validation.

        Args:
            watch_path: Directory to monitor for file changes
            supported_extensions: File extensions to monitor
            callback: Function to call when a new file is detected
            use_polling: Whether to use polling observer instead of native
            max_retries: Maximum number of retry attempts for failed operations
            base_delay: Base delay in seconds for exponential backoff
            polling_interval: Interval in seconds for polling observer
        """
        if not self._validate_config(watch_path, supported_extensions, callback):
            raise ValueError("Invalid file watcher configuration")

        self.watch_path = watch_path
        self.callback = callback
        self.use_polling = use_polling
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.polling_interval = polling_interval

        # Initialize handler with retry configuration
        self.handler = ImageFileHandler(
            callback=callback,
            supported_extensions=supported_extensions,
            max_retries=max_retries,
            base_delay=base_delay,
        )

        self.observer: BaseObserver | None = None
        self._is_running = False
        self._start_time: datetime | None = None

        # Performance tracking
        self.startup_errors = 0
        self.observer_errors = 0
        self._lock = threading.Lock()

        logger.info(
            "FileWatcher initialized - path: %s, extensions: %s, use_polling: %s",
            watch_path,
            supported_extensions,
            use_polling,
        )

    def _validate_config(
        self,
        watch_path: Path,
        supported_extensions: tuple[str, ...],
        callback: Callable[[Path], None] | Callable[[Path], bool],
    ) -> bool:
        """Validate watcher configuration.

        Args:
            watch_path: Directory to monitor
            supported_extensions: File extensions to monitor
            callback: Function to call when a new file is detected

        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            # Validate watch path
            if not isinstance(watch_path, Path):
                logger.error("Invalid watch_path: must be a Path object")
                return False

            if not watch_path.exists():
                logger.error("Watch path does not exist: %s", watch_path)
                return False

            if not watch_path.is_dir():
                logger.error("Watch path is not a directory: %s", watch_path)
                return False

            # Validate callback
            if not callable(callback):
                logger.error("Invalid callback: must be callable")
                return False

            # Validate extensions
            if not supported_extensions or not isinstance(supported_extensions, tuple):
                logger.error("Invalid supported_extensions: must be a non-empty tuple")
                return False

            if not all(isinstance(ext, str) and ext.startswith(".") for ext in supported_extensions):
                logger.error("Invalid extensions: all must be strings starting with '.'")
                return False

            return True

        except Exception as e:
            logger.error("Error validating file watcher configuration: %s", e)
            return False

    def start(self) -> None:
        """Start file monitoring with retry logic."""
        if self._is_running:
            logger.warning("File watcher is already running")
            return

        for attempt in range(self.max_retries):
            try:
                # Create observer
                if self.use_polling:
                    logger.info("Using polling observer with interval: %.1fs", self.polling_interval)
                    self.observer = PollingObserver(timeout=self.polling_interval)
                else:
                    logger.info("Using native observer")
                    self.observer = Observer()

                # Schedule handler
                self.observer.schedule(
                    self.handler,
                    path=str(self.watch_path),
                    recursive=True,
                )

                # Start observer
                self.observer.start()
                self._is_running = True
                self._start_time = datetime.now(UTC)

                logger.info("File watcher started successfully for: %s", self.watch_path)
                return

            except Exception as e:
                with self._lock:
                    self.startup_errors += 1

                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    logger.warning(
                        "Failed to start file watcher (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error("All attempts to start file watcher failed: %s", e)
                    raise

    def stop(self) -> None:
        """Stop file monitoring with error handling."""
        if not self._is_running:
            logger.warning("File watcher is not running")
            return

        try:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=10.0)  # 10 second timeout

                if self.observer.is_alive():
                    logger.warning("Observer did not stop gracefully within timeout")
                else:
                    logger.info("File watcher stopped successfully")

            self._is_running = False

        except Exception as e:
            logger.error("Error stopping file watcher: %s", e)
            with self._lock:
                self.observer_errors += 1

    def health_check(self) -> dict[str, Any]:
        """Check the health of the file watcher.

        Returns:
            Dictionary containing health status and metrics
        """
        try:
            # Basic health check
            is_healthy = self._is_running and self.observer is not None

            if self.observer:
                is_healthy = is_healthy and self.observer.is_alive()

            # Calculate uptime
            uptime_seconds = 0.0
            if self._start_time:
                uptime_seconds = (datetime.now(UTC) - self._start_time).total_seconds()

            # Get handler stats
            handler_stats = self.handler.get_stats()

            with self._lock:
                health_data = {
                    "is_healthy": is_healthy,
                    "is_running": self._is_running,
                    "observer_alive": self.observer.is_alive() if self.observer else False,
                    "use_polling": self.use_polling,
                    "watch_path": str(self.watch_path),
                    "uptime_seconds": uptime_seconds,
                    "startup_errors": self.startup_errors,
                    "observer_errors": self.observer_errors,
                    "handler_stats": handler_stats,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            logger.debug("File watcher health check completed - healthy: %s", is_healthy)
            return health_data

        except Exception as e:
            logger.error("Error during file watcher health check: %s", e)
            return {
                "is_healthy": False,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics about the file watcher.

        Returns:
            Dictionary containing performance metrics
        """
        health_data = self.health_check()
        return {
            **health_data,
            "config": {
                "max_retries": self.max_retries,
                "base_delay": self.base_delay,
                "polling_interval": self.polling_interval,
                "supported_extensions": self.handler.supported_extensions,
            },
        }

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def scan_existing_files(
    watch_path: Path,
    supported_extensions: tuple[str, ...],
    state_manager: "StateManager",
    max_files: int | None = None,
) -> list[Path]:
    """Scan for existing unprocessed files with comprehensive error handling.

    Args:
        watch_path: Directory to scan for files
        supported_extensions: File extensions to include
        state_manager: State manager to check if files are already processed
        max_files: Maximum number of files to return (None for no limit)

    Returns:
        List of unprocessed file paths

    Raises:
        ValueError: If invalid parameters are provided
    """
    unprocessed_files: list[Path] = []

    try:
        # Validate inputs
        if not isinstance(watch_path, Path):
            raise ValueError("watch_path must be a Path object")

        if not supported_extensions:
            raise ValueError("supported_extensions must not be empty")

        if max_files is not None and max_files <= 0:
            raise ValueError("max_files must be positive or None")

        # Check if directory exists
        if not watch_path.exists():
            logger.warning("Watch directory does not exist: %s", watch_path)
            return unprocessed_files

        if not watch_path.is_dir():
            logger.warning("Watch path is not a directory: %s", watch_path)
            return unprocessed_files

        logger.info("Scanning for existing files in: %s", watch_path)
        scan_start_time = time.time()

        # Counters for logging
        total_files_scanned = 0
        matching_files = 0
        already_processed = 0
        scan_errors = 0

        try:
            for file_path in watch_path.rglob("*"):
                try:
                    total_files_scanned += 1

                    # Skip if not a file
                    if not file_path.is_file():
                        continue

                    # Check extension
                    if file_path.suffix.lower() not in supported_extensions:
                        continue

                    matching_files += 1

                    # Check if already processed
                    if state_manager.is_processed(str(file_path)):
                        already_processed += 1
                        continue

                    # Add to unprocessed list
                    unprocessed_files.append(file_path)

                    # Check max files limit
                    if max_files is not None and len(unprocessed_files) >= max_files:
                        logger.info("Reached max_files limit (%d), stopping scan", max_files)
                        break

                except Exception as e:
                    scan_errors += 1
                    logger.warning("Error scanning file %s: %s", file_path, e)
                    continue

        except Exception as e:
            logger.error("Error during directory scan: %s", e)
            raise

        # Calculate scan duration
        scan_duration = time.time() - scan_start_time

        # Log comprehensive results
        logger.info(
            "File scan completed - Total: %d, Matching: %d, Already processed: %d, "
            "Unprocessed: %d, Errors: %d, Duration: %.2fs",
            total_files_scanned,
            matching_files,
            already_processed,
            len(unprocessed_files),
            scan_errors,
            scan_duration,
        )

        return unprocessed_files

    except Exception as e:
        logger.error("Failed to scan existing files: %s", e)
        raise
