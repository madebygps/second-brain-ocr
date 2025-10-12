"""Webhook notification system for file processing events."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """Sends webhook notifications for file processing events."""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)

    def notify_file_processed(
        self,
        file_path: Path,
        word_count: int,
        category: str = "",
        source: str = "",
        title: str = "",
    ) -> None:
        if not self.enabled:
            return

        payload = {
            "event": "file_processed",
            "timestamp": datetime.utcnow().isoformat(),
            "file": {
                "name": file_path.name,
                "path": str(file_path),
                "word_count": word_count,
            },
            "metadata": {
                "category": category,
                "source": source,
                "title": title,
            },
            "message": f"Processed: {title or file_path.name} ({word_count} words)",
        }

        self._send_webhook(payload)

    def notify_batch_complete(self, files_processed: int, total_time_seconds: float) -> None:
        if not self.enabled:
            return

        payload = {
            "event": "batch_complete",
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "files_processed": files_processed,
                "duration_seconds": round(total_time_seconds, 2),
            },
            "message": f"Batch complete: {files_processed} file(s) processed in {total_time_seconds:.1f}s",
        }

        self._send_webhook(payload)

    def notify_error(self, file_path: Path, error_message: str) -> None:
        if not self.enabled:
            return

        payload = {
            "event": "processing_error",
            "timestamp": datetime.utcnow().isoformat(),
            "file": {
                "name": file_path.name,
                "path": str(file_path),
            },
            "error": error_message,
            "message": f"Error processing {file_path.name}: {error_message}",
        }

        self._send_webhook(payload)

    def _send_webhook(self, payload: dict[str, Any]) -> None:
        try:
            # Check if this is a Discord webhook
            if "discord.com" in self.webhook_url:
                # Discord expects a 'content' field with the message text
                discord_payload = {"content": payload.get("message", "")}
                response = requests.post(
                    self.webhook_url,
                    json=discord_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
            else:
                # For other webhooks (ntfy.sh, Slack, etc.), send full payload
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
            response.raise_for_status()
            logger.debug("Webhook sent successfully: %s", payload.get("event"))
        except requests.RequestException as e:
            logger.warning("Failed to send webhook notification: %s", e)
