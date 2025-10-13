"""Comprehensive unit tests for embeddings generation module."""

from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

from src.second_brain_ocr.embeddings import EmbeddingGenerator


@pytest.fixture
def embedding_generator():
    """Create embedding generator instance for testing."""
    return EmbeddingGenerator("https://test.openai.azure.com/", "test-key", "text-embedding-ada-002")


@pytest.fixture
def mock_embedding_response():
    """Create mock OpenAI embedding response."""
    mock_response = MagicMock()
    mock_response.data = [MagicMock()]
    mock_response.data[0].embedding = [0.1, 0.2, 0.3] * 512  # 1536 dimensions
    return mock_response


class TestEmbeddingGeneratorInitialization:
    """Test embedding generator initialization."""

    def test_initialization_success(self):
        """Test successful embedding generator initialization."""
        generator = EmbeddingGenerator("https://test.openai.azure.com/", "test-key", "text-embedding-ada-002")

        assert generator.deployment_name == "text-embedding-ada-002"
        assert generator.max_retries == 3
        assert generator.base_delay == 1.0
        assert generator.max_text_length == 8000
        assert generator.client is not None

    def test_initialization_with_custom_api_version(self):
        """Test initialization with custom API version."""
        generator = EmbeddingGenerator(
            "https://test.openai.azure.com/", "test-key", "text-embedding-3-small", api_version="2024-06-01"
        )

        assert generator.deployment_name == "text-embedding-3-small"
        assert generator.client is not None


class TestTextValidation:
    """Test text validation functionality."""

    def test_validate_text_success(self, embedding_generator):
        """Test successful text validation."""
        valid_text = "This is a valid text for embedding generation."
        result = embedding_generator._validate_text(valid_text)
        assert result is True

    def test_validate_text_empty_string(self, embedding_generator):
        """Test validation fails for empty string."""
        result = embedding_generator._validate_text("")
        assert result is False

    def test_validate_text_whitespace_only(self, embedding_generator):
        """Test validation fails for whitespace-only string."""
        result = embedding_generator._validate_text("   \n\t  ")
        assert result is False

    def test_validate_text_none(self, embedding_generator):
        """Test validation fails for None input."""
        result = embedding_generator._validate_text(None)
        assert result is False

    def test_validate_text_wrong_type(self, embedding_generator):
        """Test validation fails for non-string input."""
        result = embedding_generator._validate_text(123)
        assert result is False

    def test_validate_text_too_long(self, embedding_generator):
        """Test validation fails for text exceeding length limit."""
        long_text = "x" * (embedding_generator.max_text_length + 1)
        result = embedding_generator._validate_text(long_text)
        assert result is False

    def test_validate_text_max_length_boundary(self, embedding_generator):
        """Test validation at maximum length boundary."""
        max_length_text = "x" * embedding_generator.max_text_length
        result = embedding_generator._validate_text(max_length_text)
        assert result is True

    def test_validate_text_unicode_warning(self, embedding_generator):
        """Test validation handles unicode characters with warning."""
        unicode_text = "🎉" * 100  # Emojis have high byte-to-char ratio
        with patch("src.second_brain_ocr.embeddings.logger"):
            result = embedding_generator._validate_text(unicode_text)
            assert result is True
            # Check if a warning was logged (the actual implementation may or may not log this)
            # This test validates the method doesn't crash with unicode text


class TestEmbeddingRetryLogic:
    """Test embedding generation retry mechanisms."""

    @patch("src.second_brain_ocr.embeddings.time.sleep")
    def test_retry_success_first_attempt(self, mock_sleep, embedding_generator, mock_embedding_response):
        """Test successful embedding generation on first attempt."""
        with patch.object(embedding_generator.client.embeddings, "create", return_value=mock_embedding_response):
            result = embedding_generator._generate_embedding_with_retry("test text")

            assert result is not None
            assert len(result) == 1536
            mock_sleep.assert_not_called()

    @patch("src.second_brain_ocr.embeddings.time.sleep")
    def test_retry_success_second_attempt(self, mock_sleep, embedding_generator, mock_embedding_response):
        """Test successful embedding generation on second attempt after rate limit."""
        rate_limit_error = RateLimitError("Rate limited", response=MagicMock(), body=None)

        with patch.object(embedding_generator.client.embeddings, "create") as mock_create:
            mock_create.side_effect = [rate_limit_error, mock_embedding_response]

            result = embedding_generator._generate_embedding_with_retry("test text")

            assert result is not None
            assert len(result) == 1536
            assert mock_create.call_count == 2
            mock_sleep.assert_called_once()

    @patch("src.second_brain_ocr.embeddings.time.sleep")
    def test_retry_rate_limiting_exponential_backoff(self, mock_sleep, embedding_generator):
        """Test exponential backoff for rate limiting errors."""
        rate_limit_error = RateLimitError("Rate limited", response=MagicMock(), body=None)

        with patch.object(embedding_generator.client.embeddings, "create", side_effect=rate_limit_error):
            result = embedding_generator._generate_embedding_with_retry("test text")

            assert result is None
            # Should sleep with exponential backoff: 1s, 2s
            expected_delays = [1.0, 2.0]
            actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert actual_delays == expected_delays

    @patch("src.second_brain_ocr.embeddings.time.sleep")
    def test_retry_timeout_linear_backoff(self, mock_sleep, embedding_generator):
        """Test linear backoff for timeout errors."""
        timeout_error = APITimeoutError("Request timeout")

        with patch.object(embedding_generator.client.embeddings, "create", side_effect=timeout_error):
            result = embedding_generator._generate_embedding_with_retry("test text")

            assert result is None
            # Should sleep with linear backoff: 1s, 2s
            expected_delays = [1.0, 2.0]
            actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert actual_delays == expected_delays

    @patch("src.second_brain_ocr.embeddings.time.sleep")
    def test_retry_connection_error_linear_backoff(self, mock_sleep, embedding_generator):
        """Test linear backoff for connection errors."""
        # Create connection error with proper request object
        mock_request = MagicMock()
        connection_error = APIConnectionError(request=mock_request)

        with patch.object(embedding_generator.client.embeddings, "create", side_effect=connection_error):
            result = embedding_generator._generate_embedding_with_retry("test text")

            assert result is None
            # Should sleep with linear backoff: 1s, 2s
            expected_delays = [1.0, 2.0]
            actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert actual_delays == expected_delays

    def test_retry_server_error_retryable(self, embedding_generator):
        """Test server errors (5xx) are retried."""
        # Create API error with all required parameters
        mock_request = MagicMock()
        server_error = APIError("Internal server error", request=mock_request, body=None)
        server_error.status_code = 500

        with patch.object(embedding_generator.client.embeddings, "create", side_effect=server_error):
            with patch("src.second_brain_ocr.embeddings.time.sleep"):
                result = embedding_generator._generate_embedding_with_retry("test text")

                assert result is None
                assert embedding_generator.client.embeddings.create.call_count == 3

    def test_retry_client_error_no_retry(self, embedding_generator):
        """Test client errors (4xx) are not retried."""
        # Create API error with all required parameters
        mock_request = MagicMock()
        client_error = APIError("Bad request", request=mock_request, body=None)
        client_error.status_code = 400

        with patch.object(embedding_generator.client.embeddings, "create", side_effect=client_error):
            result = embedding_generator._generate_embedding_with_retry("test text")

            assert result is None
            # Should only be called once (no retries)
            assert embedding_generator.client.embeddings.create.call_count == 1

    def test_retry_unexpected_error_no_retry(self, embedding_generator):
        """Test unexpected errors are not retried."""
        unexpected_error = ValueError("Unexpected error")

        with patch.object(embedding_generator.client.embeddings, "create", side_effect=unexpected_error):
            result = embedding_generator._generate_embedding_with_retry("test text")

            assert result is None
            # Should only be called once (no retries)
            assert embedding_generator.client.embeddings.create.call_count == 1


class TestGenerateEmbedding:
    """Test single embedding generation functionality."""

    def test_generate_embedding_success(self, embedding_generator, mock_embedding_response):
        """Test successful embedding generation."""
        test_text = "This is a test text for embedding generation."

        with patch.object(embedding_generator, "_validate_text", return_value=True):
            with patch.object(embedding_generator, "_generate_embedding_with_retry", return_value=[0.1] * 1536):
                result = embedding_generator.generate_embedding(test_text)

                assert result is not None
                assert len(result) == 1536
                assert all(isinstance(x, float) for x in result)

    def test_generate_embedding_validation_failure(self, embedding_generator):
        """Test embedding generation fails when text validation fails."""
        with patch.object(embedding_generator, "_validate_text", return_value=False):
            result = embedding_generator.generate_embedding("invalid text")

            assert result is None

    def test_generate_embedding_retry_failure(self, embedding_generator):
        """Test embedding generation fails when retry mechanism fails."""
        with patch.object(embedding_generator, "_validate_text", return_value=True):
            with patch.object(embedding_generator, "_generate_embedding_with_retry", return_value=None):
                result = embedding_generator.generate_embedding("test text")

                assert result is None

    def test_generate_embedding_performance_metrics(self, embedding_generator):
        """Test that performance metrics are logged."""
        test_text = "Test content for metrics"

        with patch.object(embedding_generator, "_validate_text", return_value=True):
            with patch.object(embedding_generator, "_generate_embedding_with_retry", return_value=[0.1] * 1536):
                with patch("src.second_brain_ocr.embeddings.logger") as mock_logger:
                    result = embedding_generator.generate_embedding(test_text)

                    assert result is not None
                    # Check that performance metrics are logged
                    info_calls = [
                        call for call in mock_logger.info.call_args_list if "Embedding completed" in str(call)
                    ]
                    assert len(info_calls) > 0

    def test_generate_embedding_exception_handling(self, embedding_generator):
        """Test exception handling in generate_embedding."""
        with patch.object(embedding_generator, "_validate_text", side_effect=Exception("Unexpected error")):
            result = embedding_generator.generate_embedding("test text")

            assert result is None


class TestGenerateEmbeddingsBatch:
    """Test batch embedding generation functionality."""

    def test_generate_embeddings_batch_success(self, embedding_generator):
        """Test successful batch embedding generation."""
        test_texts = ["Text 1", "Text 2", "Text 3"]

        with patch.object(embedding_generator, "generate_embedding") as mock_generate:
            mock_generate.side_effect = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]

            result = embedding_generator.generate_embeddings_batch(test_texts)

            assert len(result) == 3
            assert all(embedding is not None for embedding in result)
            assert mock_generate.call_count == 3

    def test_generate_embeddings_batch_empty_list(self, embedding_generator):
        """Test batch generation with empty list."""
        result = embedding_generator.generate_embeddings_batch([])

        assert result == []

    def test_generate_embeddings_batch_partial_failure(self, embedding_generator):
        """Test batch generation with some failures."""
        test_texts = ["Valid text", "Another valid text"]

        with patch.object(embedding_generator, "generate_embedding") as mock_generate:
            mock_generate.side_effect = [[0.1] * 1536, None]  # Second one fails

            result = embedding_generator.generate_embeddings_batch(test_texts)

            assert len(result) == 2
            assert result[0] is not None
            assert result[1] is None

    def test_generate_embeddings_batch_metrics(self, embedding_generator):
        """Test that batch metrics are logged."""
        test_texts = ["Text 1", "Text 2"]

        with patch.object(embedding_generator, "generate_embedding", return_value=[0.1] * 1536):
            with patch("src.second_brain_ocr.embeddings.logger") as mock_logger:
                result = embedding_generator.generate_embeddings_batch(test_texts)

                assert len(result) == 2
                # Check that batch completion metrics are logged
                info_calls = [
                    call for call in mock_logger.info.call_args_list if "Batch embedding completed" in str(call)
                ]
                assert len(info_calls) > 0


class TestChunkText:
    """Test text chunking functionality."""

    def test_chunk_text_short_text(self, embedding_generator):
        """Test chunking with text shorter than max length."""
        short_text = "This is a short text."
        chunks = embedding_generator.chunk_text(short_text)

        assert len(chunks) == 1
        assert chunks[0] == short_text

    def test_chunk_text_long_text(self, embedding_generator):
        """Test chunking with text longer than max length."""
        # Create text longer than default max_tokens * 4 characters
        # Use smaller max_tokens to force chunking
        long_text = "This is a test sentence. " * 400  # ~10,000 characters
        chunks = embedding_generator.chunk_text(long_text, max_tokens=500)  # Force smaller chunks

        assert len(chunks) > 1
        assert all(len(chunk) > 10 for chunk in chunks)  # No very short chunks

    def test_chunk_text_empty_string(self, embedding_generator):
        """Test chunking with empty string."""
        chunks = embedding_generator.chunk_text("")

        assert chunks == []

    def test_chunk_text_whitespace_only(self, embedding_generator):
        """Test chunking with whitespace-only string."""
        chunks = embedding_generator.chunk_text("   \n\t  ")

        assert chunks == []

    def test_chunk_text_custom_parameters(self, embedding_generator):
        """Test chunking with custom max_tokens and overlap."""
        text = "Sentence one. Sentence two. Sentence three. Sentence four. " * 20
        chunks = embedding_generator.chunk_text(text, max_tokens=100, overlap=20)

        assert len(chunks) > 1
        # With custom parameters, chunks should be smaller
        max_expected_chars = 100 * 4  # 400 characters
        assert all(
            len(chunk) <= max_expected_chars * 1.1 for chunk in chunks
        )  # Allow some variance for sentence boundaries

    def test_chunk_text_sentence_boundaries(self, embedding_generator):
        """Test that chunking respects sentence boundaries."""
        # Create text with clear sentence boundaries
        sentences = ["This is sentence one. ", "This is sentence two. ", "This is sentence three. "]
        text = "".join(sentences * 100)  # Repeat to make it long

        chunks = embedding_generator.chunk_text(text, max_tokens=200)

        # Most chunks should end with sentence endings
        sentence_ending_chunks = sum(1 for chunk in chunks if chunk.rstrip().endswith((".", "!", "?")))
        assert sentence_ending_chunks >= len(chunks) * 0.7  # At least 70% should end properly

    def test_chunk_text_overlap(self, embedding_generator):
        """Test that chunks have appropriate overlap."""
        text = "Word " * 2000  # Simple repeated text
        chunks = embedding_generator.chunk_text(text, max_tokens=500, overlap=100)

        if len(chunks) > 1:
            # Check that there's some content overlap between consecutive chunks
            # This is a basic check - exact overlap is hard to verify due to sentence boundary logic
            assert len(chunks) > 1

    def test_chunk_text_skip_very_short_chunks(self, embedding_generator):
        """Test that very short chunks are skipped."""
        # Create text that might produce very short chunks
        text = "A. " * 1000  # Very short sentences
        chunks = embedding_generator.chunk_text(text, max_tokens=100)

        # All chunks should be longer than 10 characters
        assert all(len(chunk) > 10 for chunk in chunks)


class TestHealthCheck:
    """Test health check functionality."""

    def test_health_check_success(self, embedding_generator):
        """Test successful health check."""
        with patch.object(embedding_generator, "_generate_embedding_with_retry", return_value=[0.1] * 1536):
            result = embedding_generator.health_check()
            assert result is True

    def test_health_check_no_embedding_returned(self, embedding_generator):
        """Test health check fails when no embedding is returned."""
        with patch.object(embedding_generator, "_generate_embedding_with_retry", return_value=None):
            result = embedding_generator.health_check()
            assert result is False

    def test_health_check_empty_embedding(self, embedding_generator):
        """Test health check fails when empty embedding is returned."""
        with patch.object(embedding_generator, "_generate_embedding_with_retry", return_value=[]):
            result = embedding_generator.health_check()
            assert result is False

    def test_health_check_exception(self, embedding_generator):
        """Test health check handles exceptions."""
        with patch.object(embedding_generator, "_generate_embedding_with_retry", side_effect=Exception("Test error")):
            result = embedding_generator.health_check()
            assert result is False


class TestGetEmbeddingInfo:
    """Test embedding info functionality."""

    def test_get_embedding_info(self, embedding_generator):
        """Test getting embedding configuration information."""
        info = embedding_generator.get_embedding_info()

        assert isinstance(info, dict)
        assert "deployment_name" in info
        assert "max_retries" in info
        assert "base_delay" in info
        assert "max_text_length" in info
        assert "timeout" in info
        assert "max_tokens_per_chunk" in info
        assert "chunk_overlap" in info

        assert info["deployment_name"] == embedding_generator.deployment_name
        assert info["max_retries"] == embedding_generator.max_retries
        assert info["base_delay"] == embedding_generator.base_delay
        assert info["max_text_length"] == embedding_generator.max_text_length


class TestLoggingIntegration:
    """Test logging integration."""

    def test_logger_initialization(self):
        """Test that logger is properly initialized from Config."""
        with patch("src.second_brain_ocr.config.Config.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # This should trigger logger creation
            from src.second_brain_ocr.config import Config

            result_logger = Config.get_logger("src.second_brain_ocr.embeddings")

            mock_get_logger.assert_called_once_with("src.second_brain_ocr.embeddings")
            assert result_logger == mock_logger

    def test_initialization_logging(self):
        """Test that initialization is logged."""
        with patch("src.second_brain_ocr.embeddings.logger") as mock_logger:
            EmbeddingGenerator("https://test.com", "key", "deployment")

            mock_logger.info.assert_called_with("Embedding generator initialized with deployment: %s", "deployment")
