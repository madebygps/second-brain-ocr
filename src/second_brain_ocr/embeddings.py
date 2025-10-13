"""Azure OpenAI embeddings generation."""

import time
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, AzureOpenAI, RateLimitError

from .config import Config

logger = Config.get_logger(__name__)


class EmbeddingGenerator:
    """Generates embeddings using Azure OpenAI.

    Provides robust embedding generation with retry mechanisms, comprehensive error handling,
    input validation, and performance monitoring.
    """

    def __init__(self, endpoint: str, api_key: str, deployment_name: str, api_version: str = "2024-02-01") -> None:
        self.client = AzureOpenAI(
            azure_endpoint=endpoint, api_key=api_key, api_version=api_version, timeout=Config.HTTP_TIMEOUT
        )
        self.deployment_name = deployment_name
        self.max_retries = 3
        self.base_delay = 1.0  # seconds
        self.max_text_length = 8000  # characters
        logger.info("Embedding generator initialized with deployment: %s", deployment_name)

    def _validate_text(self, text: str) -> bool:
        """Validate text input before processing.

        Args:
            text: Text to validate

        Returns:
            True if text is valid for embedding generation
        """
        if not text or not isinstance(text, str):
            logger.error("Text must be a non-empty string")
            return False

        if not text.strip():
            logger.error("Text cannot be empty or only whitespace")
            return False

        if len(text) > self.max_text_length:
            logger.error("Text too long: %d chars > %d chars limit", len(text), self.max_text_length)
            return False

        # Check for potentially problematic characters
        if len(text.encode("utf-8")) > len(text) * 4:  # Rough check for unusual encoding
            logger.warning("Text contains many non-ASCII characters, may affect embedding quality")

        logger.debug("Text validation passed: %d chars", len(text))
        return True

    def _generate_embedding_with_retry(self, text: str) -> list[float] | None:
        """Generate embedding with retry logic for transient failures.

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector or None if all retries failed
        """
        last_exception: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug("Embedding attempt %d/%d for text length %d", attempt, self.max_retries, len(text))

                response = self.client.embeddings.create(model=self.deployment_name, input=text)

                embedding_data: list[float] = list(response.data[0].embedding)

                if attempt > 1:
                    logger.info("Embedding succeeded on attempt %d", attempt)

                return embedding_data

            except RateLimitError as e:
                last_exception = e
                if attempt < self.max_retries:
                    # Exponential backoff for rate limiting
                    delay = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Rate limited on attempt %d/%d, waiting %.1fs: %s", attempt, self.max_retries, delay, e
                    )
                    time.sleep(delay)
                else:
                    logger.error("Rate limit exceeded after %d attempts", self.max_retries)

            except APITimeoutError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.base_delay * attempt  # Linear backoff for timeouts
                    logger.warning("Timeout on attempt %d/%d, waiting %.1fs: %s", attempt, self.max_retries, delay, e)
                    time.sleep(delay)
                else:
                    logger.error("Timeout after %d attempts", self.max_retries)

            except APIConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.base_delay * attempt  # Linear backoff for connection issues
                    logger.warning(
                        "Connection error on attempt %d/%d, waiting %.1fs: %s", attempt, self.max_retries, delay, e
                    )
                    time.sleep(delay)
                else:
                    logger.error("Connection failed after %d attempts", self.max_retries)

            except APIError as e:
                # For other API errors, check if they're retryable based on status code
                status_code = getattr(e, "status_code", None)
                if status_code and status_code >= 500:
                    last_exception = e
                    if attempt < self.max_retries:
                        delay = self.base_delay * attempt
                        logger.warning(
                            "Server error on attempt %d/%d, waiting %.1fs: %s", attempt, self.max_retries, delay, e
                        )
                        time.sleep(delay)
                    else:
                        logger.error("Server error after %d attempts", self.max_retries)
                else:
                    logger.error("Non-retryable API error: %s", e)
                    return None

            except Exception as e:
                logger.error("Unexpected error during embedding generation (will not retry): %s", e)
                return None

        logger.error("Embedding generation failed after %d attempts. Last error: %s", self.max_retries, last_exception)
        return None

    def generate_embedding(self, text: str) -> list[float] | None:
        """Generate embedding for a single text input.

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector as list of floats, or None if generation failed
        """
        start_time = time.time()

        try:
            logger.info("Starting embedding generation for text length: %d", len(text))

            # Validate input text
            if not self._validate_text(text):
                return None

            # Generate embedding with retry logic
            embedding_data = self._generate_embedding_with_retry(text)
            if not embedding_data:
                return None

            # Log performance metrics
            duration = time.time() - start_time
            chars_per_second = len(text) / duration if duration > 0 else 0

            logger.info(
                "Embedding completed: %d chars | %.1fs | %d dims | %.0f chars/s",
                len(text),
                duration,
                len(embedding_data),
                chars_per_second,
            )

            return embedding_data

        except Exception as e:
            duration = time.time() - start_time
            logger.exception("Unexpected error in generate_embedding after %.1fs: %s", duration, e)
            return None

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to generate embeddings for

        Returns:
            List of embedding vectors (or None for failed generations)
        """
        if not texts:
            logger.warning("Empty text list provided for batch embedding generation")
            return []

        start_time = time.time()
        logger.info("Starting batch embedding generation for %d texts", len(texts))

        embeddings = []
        successful_count = 0

        for i, text in enumerate(texts):
            logger.info("Generating embedding %d/%d", i + 1, len(texts))
            embedding = self.generate_embedding(text)
            embeddings.append(embedding)
            if embedding is not None:
                successful_count += 1

        # Log batch performance metrics
        duration = time.time() - start_time
        success_rate = successful_count / len(texts) * 100 if texts else 0

        logger.info(
            "Batch embedding completed: %d/%d successful (%.1f%%) | %.1fs total",
            successful_count,
            len(texts),
            success_rate,
            duration,
        )

        return embeddings

    def chunk_text(self, text: str, max_tokens: int | None = None, overlap: int | None = None) -> list[str]:
        """Split text into chunks suitable for embedding generation.

        Args:
            text: Text to chunk
            max_tokens: Maximum tokens per chunk (default from config)
            overlap: Token overlap between chunks (default from config)

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for chunking")
            return []

        max_tokens = max_tokens or Config.TEXT_CHUNK_MAX_TOKENS
        overlap = overlap or Config.TEXT_CHUNK_OVERLAP

        # Rough conversion: 1 token ≈ 4 characters for English text
        max_chars = max_tokens * 4
        overlap_chars = overlap * 4

        logger.debug("Chunking text: %d chars, max_tokens=%d, overlap=%d", len(text), max_tokens, overlap)

        if len(text) <= max_chars:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + max_chars

            # Try to break at sentence boundaries
            if end < len(text):
                # Look for sentence endings in order of preference
                sentence_endings = [". ", "! ", "? ", "\n\n", "\n", "; ", ", "]
                for punct in sentence_endings:
                    last_punct = text.rfind(punct, start + max_chars // 2, end)
                    if last_punct > start:
                        end = last_punct + len(punct)
                        break

            chunk = text[start:end].strip()
            if chunk and len(chunk) > 10:  # Skip very short chunks
                chunks.append(chunk)
            elif chunk:
                logger.debug("Skipping very short chunk: %d chars", len(chunk))

            # Calculate next start position with overlap
            if end >= len(text):
                break
            start = max(end - overlap_chars, start + max_chars // 2)  # Ensure progress

        logger.info(
            "Split text into %d chunks (avg %.0f chars/chunk)",
            len(chunks),
            sum(len(c) for c in chunks) / len(chunks) if chunks else 0,
        )
        return chunks

    def health_check(self) -> bool:
        """Perform a basic health check of the embedding service.

        Returns:
            True if the service is responsive, False otherwise
        """
        try:
            logger.debug("Performing embedding service health check")

            # Test with a simple, short text
            test_text = "Health check test."
            test_embedding = self._generate_embedding_with_retry(test_text)

            if test_embedding and len(test_embedding) > 0:
                logger.debug("Embedding service health check passed (dimension: %d)", len(test_embedding))
                return True
            else:
                logger.error("Embedding service health check failed: no embedding returned")
                return False

        except Exception as e:
            logger.error("Embedding service health check failed: %s", e)
            return False

    def get_embedding_info(self) -> dict[str, Any]:
        """Get information about the embedding model and configuration.

        Returns:
            Dictionary with embedding service information
        """
        return {
            "deployment_name": self.deployment_name,
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_text_length": self.max_text_length,
            "timeout": Config.HTTP_TIMEOUT,
            "max_tokens_per_chunk": Config.TEXT_CHUNK_MAX_TOKENS,
            "chunk_overlap": Config.TEXT_CHUNK_OVERLAP,
        }
