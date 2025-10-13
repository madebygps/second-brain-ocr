"""State management for tracking processed files."""

import json
import re
import threading
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Config

logger = Config.get_logger(__name__)


class StateManager:
    """Manages state of processed files to avoid reprocessing with comprehensive error handling."""

    def __init__(
        self,
        state_file: Path,
        max_retries: int = 3,
        base_delay: float = 0.5,
        auto_backup: bool = True,
    ) -> None:
        """Initialize the state manager with validation and configuration.

        Args:
            state_file: Path to the JSON state file
            max_retries: Maximum number of retry attempts for file operations
            base_delay: Base delay in seconds for exponential backoff
            auto_backup: Whether to automatically create backups before updates

        Raises:
            ValueError: If state_file is invalid
        """
        if not self._validate_config(state_file):
            raise ValueError("Invalid state manager configuration")

        self.state_file = state_file
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.auto_backup = auto_backup
        self.processed_files: set[str] = set()

        # Performance tracking
        self.load_errors = 0
        self.save_errors = 0
        self.files_marked = 0
        self.batch_operations = 0
        self.last_save_time: datetime | None = None
        self._lock = threading.Lock()
        self._creation_time = datetime.now(UTC)

        # Load initial state
        self._load_state()

        logger.info(
            "StateManager initialized - state_file: %s, auto_backup: %s",
            state_file,
            auto_backup,
        )

    def _validate_config(self, state_file: Path) -> bool:
        """Validate state manager configuration.

        Args:
            state_file: Path to validate

        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            # Validate state file path
            if not isinstance(state_file, Path):
                logger.error("Invalid state_file: must be a Path object")
                return False

            # Check if parent directory is writable (if it exists)
            if state_file.parent.exists() and not state_file.parent.is_dir():
                logger.error("Invalid state_file: parent is not a directory")
                return False

            # Validate file extension
            if state_file.suffix.lower() != ".json":
                logger.warning("State file should have .json extension: %s", state_file)

            return True

        except Exception as e:
            logger.error("Error validating state manager configuration: %s", e)
            return False

    @staticmethod
    def _normalize_path(file_path: str) -> str:
        """Normalize file path by converting unicode whitespace to regular spaces.

        Args:
            file_path: Path string to normalize

        Returns:
            Normalized path string
        """
        # Normalize unicode (NFKC form converts compatible characters to their canonical form)
        normalized = unicodedata.normalize("NFKC", file_path)
        # Replace any remaining unicode whitespace with regular space
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _load_state(self) -> None:
        """Load state from file with comprehensive error handling and retry logic."""
        if not self.state_file.exists():
            logger.info("No existing state file found, starting fresh")
            try:
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error("Failed to create state directory: %s", e)
                with self._lock:
                    self.load_errors += 1
            return

        load_start_time = time.time()

        for attempt in range(self.max_retries):
            try:
                with self.state_file.open() as f:
                    data = json.load(f)

                # Validate data structure
                if not isinstance(data, dict):
                    logger.error("Invalid state file format: expected dict, got %s", type(data))
                    raise ValueError("Invalid state file format")

                # Normalize paths when loading
                raw_paths = data.get("processed_files", [])
                if not isinstance(raw_paths, list):
                    logger.error("Invalid processed_files format: expected list, got %s", type(raw_paths))
                    raise ValueError("Invalid processed_files format")

                self.processed_files = {self._normalize_path(p) for p in raw_paths if isinstance(p, str)}

                load_duration = time.time() - load_start_time
                logger.info(
                    "Loaded %d processed files from state (%.2fs)",
                    len(self.processed_files),
                    load_duration,
                )
                return

            except json.JSONDecodeError as e:
                logger.error("Corrupted state file (invalid JSON): %s", e)
                with self._lock:
                    self.load_errors += 1

                # Try to load backup if available
                backup_file = self.state_file.with_suffix(".json.backup")
                if backup_file.exists() and attempt < self.max_retries - 1:
                    logger.info("Attempting to restore from backup: %s", backup_file)
                    try:
                        backup_file.replace(self.state_file)
                        continue  # Retry with restored backup
                    except OSError as backup_error:
                        logger.error("Failed to restore backup: %s", backup_error)

                self.processed_files = set()
                return

            except (OSError, ValueError) as e:
                with self._lock:
                    self.load_errors += 1

                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    logger.warning(
                        "Error loading state file (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error("All attempts to load state file failed: %s", e)
                    self.processed_files = set()
                    return

            except Exception as e:
                logger.exception("Unexpected error loading state file: %s", e)
                with self._lock:
                    self.load_errors += 1
                self.processed_files = set()
                return

    def _save_state(self) -> bool:
        """Save state to file with retry logic and backup creation.

        Returns:
            True if save succeeded, False otherwise
        """
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Failed to create state directory: %s", e)
            with self._lock:
                self.save_errors += 1
            return False

        # Create backup if enabled and file exists
        if self.auto_backup and self.state_file.exists():
            try:
                backup_file = self.state_file.with_suffix(".json.backup")
                self.state_file.replace(backup_file)
                logger.debug("Created backup: %s", backup_file.name)
            except OSError as e:
                logger.warning("Failed to create backup: %s", e)

        # Prepare data
        save_start_time = time.time()
        data = {
            "processed_files": sorted(self.processed_files),
            "last_updated": datetime.now(UTC).isoformat(),
            "total_files": len(self.processed_files),
            "statistics": {
                "files_marked": self.files_marked,
                "batch_operations": self.batch_operations,
                "load_errors": self.load_errors,
                "save_errors": self.save_errors,
            },
        }

        # Save with retry logic
        for attempt in range(self.max_retries):
            try:
                # Write to temporary file first
                temp_file = self.state_file.with_suffix(".json.tmp")
                with temp_file.open("w") as f:
                    json.dump(data, f, indent=2)

                # Atomic rename to actual file
                temp_file.replace(self.state_file)

                save_duration = time.time() - save_start_time
                with self._lock:
                    self.last_save_time = datetime.now(UTC)

                logger.debug(
                    "Saved state: %d files (%.3fs)",
                    len(self.processed_files),
                    save_duration,
                )
                return True

            except OSError as e:
                with self._lock:
                    self.save_errors += 1

                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    logger.warning(
                        "Error saving state file (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error("All attempts to save state file failed: %s", e)
                    return False

            except Exception as e:
                logger.exception("Unexpected error saving state file: %s", e)
                with self._lock:
                    self.save_errors += 1
                return False

        return False

    def is_processed(self, file_path: str) -> bool:
        """Check if a file has been processed.

        Args:
            file_path: Path to check

        Returns:
            True if file has been processed, False otherwise
        """
        try:
            if not file_path or not isinstance(file_path, str):
                logger.warning("Invalid file_path provided to is_processed: %s", file_path)
                return False

            normalized = self._normalize_path(file_path)
            return normalized in self.processed_files

        except Exception as e:
            logger.error("Error checking if file is processed: %s", e)
            return False

    def mark_processed(self, file_path: str) -> bool:
        """Mark a file as processed.

        Args:
            file_path: Path to mark as processed

        Returns:
            True if successfully marked and saved, False otherwise
        """
        try:
            if not file_path or not isinstance(file_path, str):
                logger.warning("Invalid file_path provided to mark_processed: %s", file_path)
                return False

            normalized = self._normalize_path(file_path)

            # Check if already processed
            if normalized in self.processed_files:
                logger.debug("File already marked as processed: %s", file_path)
                return True

            # Add to processed set
            self.processed_files.add(normalized)

            # Update statistics
            with self._lock:
                self.files_marked += 1

            # Save state
            success = self._save_state()

            if success:
                logger.debug("Marked as processed: %s", file_path)
            else:
                logger.error("Failed to save state after marking file: %s", file_path)

            return success

        except Exception as e:
            logger.error("Error marking file as processed: %s", e)
            return False

    def mark_batch_processed(self, file_paths: list[str]) -> bool:
        """Mark multiple files as processed in a batch.

        Args:
            file_paths: List of paths to mark as processed

        Returns:
            True if successfully marked and saved, False otherwise
        """
        try:
            if not file_paths:
                logger.warning("Empty file_paths list provided to mark_batch_processed")
                return False

            if not isinstance(file_paths, list):
                logger.warning("Invalid file_paths type: expected list, got %s", type(file_paths))
                return False

            batch_start_time = time.time()

            # Normalize and filter valid paths
            valid_paths = []
            for path in file_paths:
                if path and isinstance(path, str):
                    valid_paths.append(path)
                else:
                    logger.warning("Skipping invalid path in batch: %s", path)

            if not valid_paths:
                logger.warning("No valid paths in batch to mark as processed")
                return False

            # Normalize paths
            normalized_paths = {self._normalize_path(p) for p in valid_paths}

            # Count new files (not already processed)
            new_files = normalized_paths - self.processed_files
            new_count = len(new_files)

            # Update processed files
            self.processed_files.update(normalized_paths)

            # Update statistics
            with self._lock:
                self.files_marked += new_count
                self.batch_operations += 1

            # Save state
            success = self._save_state()

            batch_duration = time.time() - batch_start_time

            if success:
                logger.info(
                    "Marked %d files as processed (%d new, %.2fs)",
                    len(valid_paths),
                    new_count,
                    batch_duration,
                )
            else:
                logger.error("Failed to save state after batch marking")

            return success

        except Exception as e:
            logger.error("Error marking batch as processed: %s", e)
            return False

    def get_processed_count(self) -> int:
        """Get the number of processed files.

        Returns:
            Count of processed files
        """
        return len(self.processed_files)

    def clear_processed(self) -> bool:
        """Clear all processed files from state.

        Returns:
            True if successfully cleared and saved, False otherwise
        """
        try:
            previous_count = len(self.processed_files)
            self.processed_files.clear()

            success = self._save_state()

            if success:
                logger.info("Cleared %d processed files from state", previous_count)
            else:
                logger.error("Failed to save state after clearing")

            return success

        except Exception as e:
            logger.error("Error clearing processed files: %s", e)
            return False

    def remove_processed(self, file_path: str) -> bool:
        """Remove a specific file from processed state.

        Args:
            file_path: Path to remove from processed state

        Returns:
            True if successfully removed and saved, False otherwise
        """
        try:
            if not file_path or not isinstance(file_path, str):
                logger.warning("Invalid file_path provided to remove_processed: %s", file_path)
                return False

            normalized = self._normalize_path(file_path)

            if normalized not in self.processed_files:
                logger.debug("File not in processed state: %s", file_path)
                return True

            self.processed_files.discard(normalized)
            success = self._save_state()

            if success:
                logger.debug("Removed from processed state: %s", file_path)
            else:
                logger.error("Failed to save state after removing file: %s", file_path)

            return success

        except Exception as e:
            logger.error("Error removing file from processed state: %s", e)
            return False

    def health_check(self) -> dict[str, Any]:
        """Check the health of the state manager.

        Returns:
            Dictionary containing health status and metrics
        """
        try:
            # Check if state file is accessible
            state_file_exists = self.state_file.exists()
            state_file_readable = False
            state_file_writable = False

            if state_file_exists:
                try:
                    state_file_readable = self.state_file.is_file()
                    # Test write access
                    test_file = self.state_file.with_suffix(".json.test")
                    test_file.touch()
                    test_file.unlink()
                    state_file_writable = True
                except OSError:
                    state_file_writable = False

            # Calculate uptime
            uptime_seconds = (datetime.now(UTC) - self._creation_time).total_seconds()

            # Determine overall health
            is_healthy = (
                (state_file_writable or not state_file_exists) and self.load_errors < 5 and self.save_errors < 5
            )

            with self._lock:
                health_data = {
                    "is_healthy": is_healthy,
                    "state_file": str(self.state_file),
                    "state_file_exists": state_file_exists,
                    "state_file_readable": state_file_readable,
                    "state_file_writable": state_file_writable,
                    "processed_files_count": len(self.processed_files),
                    "files_marked": self.files_marked,
                    "batch_operations": self.batch_operations,
                    "load_errors": self.load_errors,
                    "save_errors": self.save_errors,
                    "last_save_time": self.last_save_time.isoformat() if self.last_save_time else None,
                    "uptime_seconds": uptime_seconds,
                    "auto_backup": self.auto_backup,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            logger.debug("State manager health check completed - healthy: %s", is_healthy)
            return health_data

        except Exception as e:
            logger.error("Error during state manager health check: %s", e)
            return {
                "is_healthy": False,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics about the state manager.

        Returns:
            Dictionary containing performance metrics
        """
        health_data = self.health_check()

        with self._lock:
            stats = {
                **health_data,
                "config": {
                    "max_retries": self.max_retries,
                    "base_delay": self.base_delay,
                    "auto_backup": self.auto_backup,
                },
            }

        return stats
