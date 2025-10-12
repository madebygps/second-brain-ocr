"""State management for tracking processed files."""

import json
import logging
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class StateManager:
    """Manages state of processed files to avoid reprocessing."""

    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self.processed_files: set[str] = set()
        self._load_state()

    @staticmethod
    def _normalize_path(file_path: str) -> str:
        """Normalize file path by converting unicode whitespace to regular spaces."""
        # Normalize unicode (NFKC form converts compatible characters to their canonical form)
        normalized = unicodedata.normalize("NFKC", file_path)
        # Replace any remaining unicode whitespace with regular space
        import re

        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _load_state(self) -> None:
        if not self.state_file.exists():
            logger.info("No existing state file found, starting fresh")
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            return

        try:
            with self.state_file.open() as f:
                data = json.load(f)
                # Normalize paths when loading
                raw_paths = data.get("processed_files", [])
                self.processed_files = {self._normalize_path(p) for p in raw_paths}
            logger.info("Loaded %d processed files from state", len(self.processed_files))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Error loading state file: %s", e)
            self.processed_files = set()

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = {
                "processed_files": sorted(self.processed_files),
                "last_updated": datetime.now(UTC).isoformat(),
            }
            with self.state_file.open("w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.error("Error saving state file: %s", e)

    def is_processed(self, file_path: str) -> bool:
        normalized = self._normalize_path(file_path)
        return normalized in self.processed_files

    def mark_processed(self, file_path: str) -> None:
        normalized = self._normalize_path(file_path)
        self.processed_files.add(normalized)
        self._save_state()
        logger.debug("Marked as processed: %s", file_path)

    def mark_batch_processed(self, file_paths: list[str]) -> None:
        normalized_paths = {self._normalize_path(p) for p in file_paths}
        self.processed_files.update(normalized_paths)
        self._save_state()
        logger.info("Marked %d files as processed", len(file_paths))
