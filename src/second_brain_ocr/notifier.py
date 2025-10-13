"""Webhook notification system for file processing events."""

import threading
import time
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry  # type: ignore[import-not-found]
except ImportError:
    from urllib3.util import Retry  # type: ignore[import-not-found]

from .config import Config

logger = Config.get_logger(__name__)


class WebhookProvider(Enum):
    """Supported webhook providers with different payload formats."""

    DISCORD = "discord"
    SLACK = "slack"
    NTFY = "ntfy"
    GENERIC = "generic"


class WebhookNotifier:
    """Sends webhook notifications for file processing events with comprehensive error handling."""

    def __init__(
        self,
        webhook_url: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
        timeout: float | None = None,
    ) -> None:
        """Initialize the webhook notifier with validation and retry configuration.

        Args:
            webhook_url: URL for webhook notifications (empty string to disable)
            max_retries: Maximum number of retry attempts for failed webhooks
            base_delay: Base delay in seconds for exponential backoff
            timeout: Request timeout in seconds (uses Config.HTTP_TIMEOUT if None)

        Raises:
            ValueError: If webhook_url is invalid when provided
        """
        self.webhook_url = webhook_url.strip() if webhook_url else ""
        self.enabled = bool(self.webhook_url)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout if timeout is not None else Config.HTTP_TIMEOUT

        # Detect webhook provider
        self.provider = self._detect_provider()

        # Performance tracking
        self.notifications_sent = 0
        self.notifications_failed = 0
        self.total_retry_attempts = 0
        self.last_notification_time: datetime | None = None
        self._lock = threading.Lock()

        # Configure requests session with retry logic
        self.session = self._create_session()

        if self.enabled:
            # Validate webhook URL
            if not self._validate_webhook_url():
                raise ValueError(f"Invalid webhook URL: {self.webhook_url}")

            logger.info(
                "WebhookNotifier initialized - provider: %s, max_retries: %d, enabled: %s",
                self.provider.value,
                max_retries,
                self.enabled,
            )
        else:
            logger.info("WebhookNotifier disabled (no webhook URL provided)")

    def _validate_webhook_url(self) -> bool:
        """Validate webhook URL format.

        Returns:
            True if URL is valid, False otherwise
        """
        try:
            if not self.webhook_url:
                return True  # Empty URL is valid (disabled)

            # Check if it's a valid URL
            if not self.webhook_url.startswith(("http://", "https://")):
                logger.error("Webhook URL must start with http:// or https://")
                return False

            # Basic URL structure validation
            from urllib.parse import urlparse

            parsed = urlparse(self.webhook_url)
            if not parsed.netloc:
                logger.error("Invalid webhook URL: missing domain")
                return False

            return True

        except Exception as e:
            logger.error("Error validating webhook URL: %s", e)
            return False

    def _detect_provider(self) -> WebhookProvider:
        """Detect webhook provider from URL.

        Returns:
            WebhookProvider enum value
        """
        if not self.webhook_url:
            return WebhookProvider.GENERIC

        url_lower = self.webhook_url.lower()

        if "discord.com" in url_lower or "discordapp.com" in url_lower:
            return WebhookProvider.DISCORD
        elif "slack.com" in url_lower:
            return WebhookProvider.SLACK
        elif "ntfy.sh" in url_lower or "/ntfy/" in url_lower:
            return WebhookProvider.NTFY
        else:
            return WebhookProvider.GENERIC

    def _create_session(self) -> requests.Session:
        """Create requests session with retry configuration.

        Returns:
            Configured requests.Session object
        """
        session = requests.Session()

        # Configure retry strategy for transient failures
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.base_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def notify_file_processed(
        self,
        file_path: Path,
        word_count: int,
        category: str = "",
        source: str = "",
        title: str = "",
    ) -> bool:
        """Notify that a file has been processed.

        Args:
            file_path: Path to the processed file
            word_count: Number of words extracted
            category: Optional category classification
            source: Optional source information
            title: Optional document title

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            return True

        try:
            # Validate inputs
            if not isinstance(file_path, Path):
                logger.warning("Invalid file_path type: %s", type(file_path))
                return False

            if not isinstance(word_count, int):
                logger.warning("Invalid word_count type: %s", type(word_count))
                return False

            payload = {
                "event": "file_processed",
                "timestamp": datetime.now(UTC).isoformat(),
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
                "message": f"✅ Processed: {title or file_path.name} ({word_count} words)",
            }

            return self._send_webhook(payload)

        except Exception as e:
            logger.error("Error in notify_file_processed: %s", e)
            return False

    def notify_batch_complete(self, files_processed: int, total_time_seconds: float) -> bool:
        """Notify that a batch of files has been processed.

        Args:
            files_processed: Number of files processed in the batch
            total_time_seconds: Total processing time in seconds

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            return True

        try:
            # Validate inputs
            if not isinstance(files_processed, int) or files_processed < 0:
                logger.warning("Invalid files_processed: %s", files_processed)
                return False

            if not isinstance(total_time_seconds, (int, float)) or total_time_seconds < 0:
                logger.warning("Invalid total_time_seconds: %s", total_time_seconds)
                return False

            # Calculate average time per file
            avg_time = total_time_seconds / max(files_processed, 1)

            payload = {
                "event": "batch_complete",
                "timestamp": datetime.now(UTC).isoformat(),
                "summary": {
                    "files_processed": files_processed,
                    "duration_seconds": round(total_time_seconds, 2),
                    "avg_time_per_file": round(avg_time, 2),
                },
                "message": f"🎉 Batch complete: {files_processed} file(s) processed in {total_time_seconds:.1f}s",
            }

            return self._send_webhook(payload)

        except Exception as e:
            logger.error("Error in notify_batch_complete: %s", e)
            return False

    def notify_error(self, file_path: Path, error_message: str) -> bool:
        """Notify that an error occurred during processing.

        Args:
            file_path: Path to the file that caused the error
            error_message: Description of the error

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            return True

        try:
            # Validate inputs
            if not isinstance(file_path, Path):
                logger.warning("Invalid file_path type: %s", type(file_path))
                return False

            if not error_message or not isinstance(error_message, str):
                logger.warning("Invalid error_message: %s", error_message)
                return False

            payload = {
                "event": "processing_error",
                "timestamp": datetime.now(UTC).isoformat(),
                "file": {
                    "name": file_path.name,
                    "path": str(file_path),
                },
                "error": error_message,
                "message": f"❌ Error processing {file_path.name}: {error_message}",
            }

            return self._send_webhook(payload)

        except Exception as e:
            logger.error("Error in notify_error: %s", e)
            return False

    def _send_webhook(self, payload: dict[str, Any]) -> bool:
        """Send webhook with retry logic and provider-specific formatting.

        Args:
            payload: Webhook payload data

        Returns:
            True if webhook sent successfully, False otherwise
        """
        if not self.enabled:
            return True

        send_start_time = time.time()
        event_type = payload.get("event", "unknown")

        for attempt in range(self.max_retries):
            try:
                # Format payload for specific provider
                formatted_payload = self._format_payload_for_provider(payload)

                # Send request
                response = self.session.post(
                    self.webhook_url,
                    json=formatted_payload,
                    headers=self._get_headers(),
                    timeout=self.timeout,
                )

                response.raise_for_status()

                send_duration = time.time() - send_start_time

                # Update statistics
                with self._lock:
                    self.notifications_sent += 1
                    self.last_notification_time = datetime.now(UTC)
                    if attempt > 0:
                        self.total_retry_attempts += attempt

                logger.debug(
                    "Webhook sent successfully - event: %s, attempt: %d/%d, duration: %.2fs",
                    event_type,
                    attempt + 1,
                    self.max_retries,
                    send_duration,
                )
                return True

            except requests.Timeout as e:
                with self._lock:
                    if attempt == self.max_retries - 1:
                        self.notifications_failed += 1

                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    logger.warning(
                        "Webhook timeout (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error("All webhook attempts timed out for event: %s", event_type)
                    return False

            except requests.HTTPError as e:
                with self._lock:
                    if attempt == self.max_retries - 1:
                        self.notifications_failed += 1

                # Don't retry on client errors (4xx)
                if e.response is not None and 400 <= e.response.status_code < 500:
                    logger.error(
                        "Webhook client error (%d): %s",
                        e.response.status_code,
                        e.response.text[:200],
                    )
                    return False

                # Retry on server errors (5xx)
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    logger.warning(
                        "Webhook server error (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error("All webhook attempts failed for event: %s", event_type)
                    return False

            except requests.RequestException as e:
                with self._lock:
                    if attempt == self.max_retries - 1:
                        self.notifications_failed += 1

                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    logger.warning(
                        "Webhook request error (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error("All webhook attempts failed for event: %s", event_type)
                    return False

            except Exception as e:
                logger.exception("Unexpected error sending webhook: %s", e)
                with self._lock:
                    self.notifications_failed += 1
                return False

        return False

    def _format_payload_for_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Format payload based on webhook provider requirements.

        Args:
            payload: Generic webhook payload

        Returns:
            Provider-specific formatted payload
        """
        message = payload.get("message", "")

        if self.provider == WebhookProvider.DISCORD:
            # Discord expects 'content' field
            return {"content": message}

        elif self.provider == WebhookProvider.SLACK:
            # Slack expects 'text' field
            return {"text": message}

        elif self.provider == WebhookProvider.NTFY:
            # ntfy.sh expects 'topic' and 'message' fields
            return {
                "topic": "second-brain-ocr",
                "message": message,
                "title": payload.get("event", "Notification"),
                "priority": self._get_ntfy_priority(payload.get("event", "")),
            }

        else:
            # Generic webhook - send full payload
            return payload

    def _get_ntfy_priority(self, event: str) -> int:
        """Get ntfy priority based on event type.

        Args:
            event: Event type

        Returns:
            Priority level (1-5)
        """
        if "error" in event.lower():
            return 4  # High priority for errors
        elif "batch_complete" in event.lower():
            return 3  # Default priority for batch completion
        else:
            return 2  # Low priority for file processing

    def _get_headers(self) -> dict[str, str]:
        """Get request headers for webhook.

        Returns:
            Dictionary of HTTP headers
        """
        return {
            "Content-Type": "application/json",
            "User-Agent": "SecondBrainOCR/1.0",
        }

    def health_check(self) -> dict[str, Any]:
        """Check the health of the webhook notifier.

        Returns:
            Dictionary containing health status and metrics
        """
        try:
            # Basic health check
            is_healthy = True

            if self.enabled:
                # Check if webhook URL is still valid
                is_healthy = self._validate_webhook_url()

                # Check error rate
                total_notifications = self.notifications_sent + self.notifications_failed
                if total_notifications > 0:
                    error_rate = (self.notifications_failed / total_notifications) * 100
                    # Consider unhealthy if error rate > 50%
                    is_healthy = is_healthy and error_rate < 50.0

            with self._lock:
                health_data = {
                    "is_healthy": is_healthy,
                    "enabled": self.enabled,
                    "provider": self.provider.value,
                    "webhook_url_configured": bool(self.webhook_url),
                    "notifications_sent": self.notifications_sent,
                    "notifications_failed": self.notifications_failed,
                    "total_retry_attempts": self.total_retry_attempts,
                    "last_notification_time": (
                        self.last_notification_time.isoformat() if self.last_notification_time else None
                    ),
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            logger.debug("Webhook notifier health check completed - healthy: %s", is_healthy)
            return health_data

        except Exception as e:
            logger.error("Error during webhook notifier health check: %s", e)
            return {
                "is_healthy": False,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics about the webhook notifier.

        Returns:
            Dictionary containing performance metrics
        """
        health_data = self.health_check()

        # Calculate success rate
        total_notifications = self.notifications_sent + self.notifications_failed
        success_rate = (self.notifications_sent / total_notifications * 100) if total_notifications > 0 else 100.0

        return {
            **health_data,
            "statistics": {
                "total_notifications": total_notifications,
                "success_rate": round(success_rate, 2),
                "avg_retries_per_failure": (
                    round(self.total_retry_attempts / max(self.notifications_failed, 1), 2)
                    if self.notifications_failed > 0
                    else 0.0
                ),
            },
            "config": {
                "max_retries": self.max_retries,
                "base_delay": self.base_delay,
                "timeout": self.timeout,
            },
        }

    def test_webhook(self) -> bool:
        """Send a test notification to verify webhook configuration.

        Returns:
            True if test notification sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Cannot test webhook: notifier is disabled")
            return False

        payload = {
            "event": "test_notification",
            "timestamp": datetime.now(UTC).isoformat(),
            "message": "🧪 Test notification from Second Brain OCR",
        }

        logger.info("Sending test webhook notification...")
        success = self._send_webhook(payload)

        if success:
            logger.info("Test webhook sent successfully")
        else:
            logger.error("Test webhook failed")

        return success

    def close(self) -> None:
        """Close the webhook notifier and cleanup resources."""
        try:
            if hasattr(self, "session"):
                self.session.close()
            logger.debug("WebhookNotifier closed")
        except Exception as e:
            logger.error("Error closing webhook notifier: %s", e)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
