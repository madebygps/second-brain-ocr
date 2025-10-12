"""File system watcher with event-based monitoring and polling fallback."""

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

if TYPE_CHECKING:
    from watchdog.observers.api import BaseObserver

    from .state import StateManager

logger = logging.getLogger(__name__)


class ImageFileHandler(FileSystemEventHandler):
    """Handler for new image file events."""

    def __init__(self, callback: Callable[[Path], None], supported_extensions: tuple[str, ...]) -> None:
        self.callback = callback
        self.supported_extensions = supported_extensions

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        file_path = Path(str(event.src_path))

        if file_path.suffix.lower() in self.supported_extensions:
            logger.info("New file detected: %s", file_path)
            time.sleep(1)
            self.callback(file_path)


class FileWatcher:
    """Watches directory for new image files with event-based and polling fallback."""

    def __init__(
        self,
        watch_path: Path,
        callback: Callable[[Path], None],
        supported_extensions: tuple[str, ...],
        polling_interval: int = 180,
        use_polling: bool = False,
    ) -> None:
        self.watch_path = watch_path
        self.callback = callback
        self.supported_extensions = supported_extensions
        self.polling_interval = polling_interval
        self.use_polling = use_polling
        self.observer: BaseObserver | None = None
        self.event_handler = ImageFileHandler(callback, supported_extensions)

    def start(self) -> None:
        if not self.watch_path.exists():
            logger.warning("Watch directory does not exist: %s", self.watch_path)
            logger.info("Creating watch directory...")
            self.watch_path.mkdir(parents=True, exist_ok=True)

        if self.use_polling:
            logger.info("Starting polling observer (interval: %ds)", self.polling_interval)
            self.observer = PollingObserver(timeout=self.polling_interval)
        else:
            try:
                logger.info("Starting event-based observer")
                self.observer = Observer()
            except Exception as e:
                logger.warning("Failed to start event-based observer: %s", e)
                logger.info("Falling back to polling observer (interval: %ds)", self.polling_interval)
                self.observer = PollingObserver(timeout=self.polling_interval)
                self.use_polling = True

        self.observer.schedule(self.event_handler, str(self.watch_path), recursive=True)
        self.observer.start()

        mode = "polling" if self.use_polling else "event-based"
        logger.info("File watcher started in %s mode, watching: %s", mode, self.watch_path)

    def stop(self) -> None:
        if self.observer:
            logger.info("Stopping file watcher...")
            self.observer.stop()
            self.observer.join()
            logger.info("File watcher stopped")

    def is_alive(self) -> bool:
        return self.observer is not None and self.observer.is_alive()


def scan_existing_files(
    watch_path: Path,
    supported_extensions: tuple[str, ...],
    state_manager: "StateManager",
) -> list[Path]:
    unprocessed_files: list[Path] = []

    if not watch_path.exists():
        logger.warning("Watch directory does not exist: %s", watch_path)
        return unprocessed_files

    logger.info("Scanning for existing files in: %s", watch_path)

    for file_path in watch_path.rglob("*"):
        if (
            file_path.is_file()
            and file_path.suffix.lower() in supported_extensions
            and not state_manager.is_processed(str(file_path))
        ):
            unprocessed_files.append(file_path)

    logger.info("Found %d unprocessed files", len(unprocessed_files))
    return unprocessed_files
