"""Unit tests for OCR processing module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    HttpResponseError,
)

from src.second_brain_ocr.config import Config
from src.second_brain_ocr.ocr import OCRProcessor


@pytest.fixture
def ocr_processor():
    """Create OCR processor instance for testing."""
    return OCRProcessor("https://test.cognitiveservices.azure.com/", "test-key")


@pytest.fixture
def mock_file(tmp_path):
    """Create a temporary mock file for testing."""
    test_file = tmp_path / "test.jpg"
    test_file.write_bytes(b"fake image data" * 1000)  # ~15KB file
    return test_file


@pytest.fixture
def mock_large_file(tmp_path):
    """Create a large temporary file for size limit testing."""
    test_file = tmp_path / "large.jpg"
    # Create a file larger than 50MB
    test_file.write_bytes(b"x" * (51 * 1024 * 1024))
    return test_file


class TestOCRProcessorInitialization:
    """Test OCR processor initialization."""

    def test_initialization_success(self):
        """Test successful OCR processor initialization."""
        processor = OCRProcessor("https://test.cognitiveservices.azure.com/", "test-key")

        assert processor.max_retries == 3
        assert processor.base_delay == 1.0
        assert processor.client is not None

    def test_initialization_with_custom_endpoint(self):
        """Test initialization with custom endpoint."""
        custom_endpoint = "https://custom.cognitiveservices.azure.com/"
        processor = OCRProcessor(custom_endpoint, "test-key")

        assert processor.client is not None


class TestFileValidation:
    """Test file validation functionality."""

    def test_validate_file_success(self, ocr_processor, mock_file):
        """Test successful file validation."""
        result = ocr_processor._validate_file(mock_file)
        assert result is True

    def test_validate_file_nonexistent(self, ocr_processor, tmp_path):
        """Test validation fails for nonexistent file."""
        nonexistent = tmp_path / "nonexistent.jpg"
        result = ocr_processor._validate_file(nonexistent)
        assert result is False

    def test_validate_file_unsupported_extension(self, ocr_processor, tmp_path):
        """Test validation fails for unsupported file extension."""
        unsupported = tmp_path / "test.txt"
        unsupported.write_text("test content")
        result = ocr_processor._validate_file(unsupported)
        assert result is False

    def test_validate_file_supported_extensions(self, ocr_processor, tmp_path):
        """Test validation succeeds for all supported extensions."""
        for ext in Config.SUPPORTED_IMAGE_EXTENSIONS:
            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(b"fake data")
            result = ocr_processor._validate_file(test_file)
            assert result is True, f"Extension {ext} should be supported"

    def test_validate_file_too_large(self, ocr_processor, mock_large_file):
        """Test validation fails for files larger than 50MB."""
        result = ocr_processor._validate_file(mock_large_file)
        assert result is False

    def test_validate_file_directory_not_file(self, ocr_processor, tmp_path):
        """Test validation fails when path is a directory."""
        directory = tmp_path / "test_dir.jpg"  # Has image extension but is directory
        directory.mkdir()
        result = ocr_processor._validate_file(directory)
        assert result is False

    def test_validate_file_permission_error(self, ocr_processor, tmp_path):
        """Test validation handles OSError gracefully."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"data")

        with patch.object(Path, "exists", side_effect=OSError("Permission denied")):
            result = ocr_processor._validate_file(test_file)
            assert result is False


class TestOCRRetryLogic:
    """Test OCR retry mechanisms."""

    @patch("src.second_brain_ocr.ocr.time.sleep")
    def test_retry_success_first_attempt(self, mock_sleep, ocr_processor, mock_file):
        """Test successful OCR on first attempt."""
        mock_result = MagicMock()
        mock_result.content = "extracted text"

        mock_poller = MagicMock()
        mock_poller.result.return_value = mock_result

        with patch.object(ocr_processor.client, "begin_analyze_document", return_value=mock_poller):
            result = ocr_processor._perform_ocr_with_retry(mock_file)

            assert result == mock_result
            mock_sleep.assert_not_called()

    @patch("src.second_brain_ocr.ocr.time.sleep")
    def test_retry_success_second_attempt(self, mock_sleep, ocr_processor, mock_file):
        """Test successful OCR on second attempt after HTTP error."""
        mock_result = MagicMock()
        mock_result.content = "extracted text"

        mock_poller = MagicMock()
        mock_poller.result.return_value = mock_result

        # First call raises HttpResponseError, second succeeds
        http_error = HttpResponseError("Server error")
        http_error.status_code = 500

        with patch.object(ocr_processor.client, "begin_analyze_document") as mock_analyze:
            mock_analyze.side_effect = [http_error, mock_poller]

            result = ocr_processor._perform_ocr_with_retry(mock_file)

            assert result == mock_result
            assert mock_analyze.call_count == 2
            mock_sleep.assert_called_once()

    @patch("src.second_brain_ocr.ocr.time.sleep")
    def test_retry_rate_limiting_exponential_backoff(self, mock_sleep, ocr_processor, mock_file):
        """Test exponential backoff for rate limiting (429) errors."""
        rate_limit_error = HttpResponseError("Rate limited")
        rate_limit_error.status_code = 429

        with patch.object(ocr_processor.client, "begin_analyze_document", side_effect=rate_limit_error):
            result = ocr_processor._perform_ocr_with_retry(mock_file)

            assert result is None
            # Should sleep with exponential backoff: 1s, 2s
            expected_delays = [1.0, 2.0]  # base_delay * (2^(attempt-1))
            actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert actual_delays == expected_delays

    @patch("src.second_brain_ocr.ocr.time.sleep")
    def test_retry_server_error_linear_backoff(self, mock_sleep, ocr_processor, mock_file):
        """Test linear backoff for server (5xx) errors."""
        server_error = HttpResponseError("Internal server error")
        server_error.status_code = 500

        with patch.object(ocr_processor.client, "begin_analyze_document", side_effect=server_error):
            result = ocr_processor._perform_ocr_with_retry(mock_file)

            assert result is None
            # Should sleep with linear backoff: 1s, 2s
            expected_delays = [1.0, 2.0]  # base_delay * attempt
            actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert actual_delays == expected_delays

    def test_retry_authentication_error_no_retry(self, ocr_processor, mock_file):
        """Test authentication errors are not retried."""
        auth_error = ClientAuthenticationError("Invalid credentials")

        with patch.object(ocr_processor.client, "begin_analyze_document", side_effect=auth_error):
            result = ocr_processor._perform_ocr_with_retry(mock_file)

            assert result is None
            # Should only be called once (no retries)
            assert ocr_processor.client.begin_analyze_document.call_count == 1

    def test_retry_client_error_no_retry(self, ocr_processor, mock_file):
        """Test client errors (4xx except 429) are not retried."""
        client_error = HttpResponseError("Bad request")
        client_error.status_code = 400

        with patch.object(ocr_processor.client, "begin_analyze_document", side_effect=client_error):
            result = ocr_processor._perform_ocr_with_retry(mock_file)

            assert result is None
            # Should only be called once (no retries)
            assert ocr_processor.client.begin_analyze_document.call_count == 1

    @patch("src.second_brain_ocr.ocr.time.sleep")
    def test_retry_azure_error_with_backoff(self, mock_sleep, ocr_processor, mock_file):
        """Test Azure errors are retried with linear backoff."""
        azure_error = AzureError("Azure service error")

        with patch.object(ocr_processor.client, "begin_analyze_document", side_effect=azure_error):
            result = ocr_processor._perform_ocr_with_retry(mock_file)

            assert result is None
            assert mock_sleep.call_count == 2  # 2 retries after initial failure

    def test_retry_unexpected_error_no_retry(self, ocr_processor, mock_file):
        """Test unexpected errors are not retried."""
        unexpected_error = ValueError("Unexpected error")

        with patch.object(ocr_processor.client, "begin_analyze_document", side_effect=unexpected_error):
            result = ocr_processor._perform_ocr_with_retry(mock_file)

            assert result is None
            # Should only be called once (no retries)
            assert ocr_processor.client.begin_analyze_document.call_count == 1

    def test_retry_http_error_without_status_code(self, ocr_processor, mock_file):
        """Test HTTP errors without status_code attribute."""
        http_error = HttpResponseError("Network error")
        # Don't set status_code to test the fallback path

        with patch.object(ocr_processor.client, "begin_analyze_document", side_effect=http_error):
            with patch("src.second_brain_ocr.ocr.time.sleep"):
                result = ocr_processor._perform_ocr_with_retry(mock_file)

                assert result is None
                assert ocr_processor.client.begin_analyze_document.call_count == 3  # All retries attempted


class TestExtractText:
    """Test text extraction functionality."""

    def test_extract_text_success(self, ocr_processor, mock_file):
        """Test successful text extraction."""
        expected_text = "This is extracted text from the document."

        mock_result = MagicMock()
        mock_result.content = expected_text

        with patch.object(ocr_processor, "_validate_file", return_value=True):
            with patch.object(ocr_processor, "_perform_ocr_with_retry", return_value=mock_result):
                result = ocr_processor.extract_text(mock_file)

                assert result == expected_text

    def test_extract_text_validation_failure(self, ocr_processor, mock_file):
        """Test text extraction fails when file validation fails."""
        with patch.object(ocr_processor, "_validate_file", return_value=False):
            result = ocr_processor.extract_text(mock_file)

            assert result is None

    def test_extract_text_ocr_failure(self, ocr_processor, mock_file):
        """Test text extraction fails when OCR fails."""
        with patch.object(ocr_processor, "_validate_file", return_value=True):
            with patch.object(ocr_processor, "_perform_ocr_with_retry", return_value=None):
                result = ocr_processor.extract_text(mock_file)

                assert result is None

    def test_extract_text_empty_content(self, ocr_processor, mock_file):
        """Test text extraction with empty OCR result."""
        mock_result = MagicMock()
        mock_result.content = None

        with patch.object(ocr_processor, "_validate_file", return_value=True):
            with patch.object(ocr_processor, "_perform_ocr_with_retry", return_value=mock_result):
                result = ocr_processor.extract_text(mock_file)

                assert result == ""

    def test_extract_text_performance_metrics(self, ocr_processor, mock_file):
        """Test that performance metrics are logged."""
        expected_text = "Test content for metrics"

        mock_result = MagicMock()
        mock_result.content = expected_text

        with patch.object(ocr_processor, "_validate_file", return_value=True):
            with patch.object(ocr_processor, "_perform_ocr_with_retry", return_value=mock_result):
                with patch("src.second_brain_ocr.ocr.logger") as mock_logger:
                    result = ocr_processor.extract_text(mock_file)

                    assert result == expected_text
                    # Check that performance metrics are logged
                    info_calls = [call for call in mock_logger.info.call_args_list if "OCR completed" in str(call)]
                    assert len(info_calls) > 0

    def test_extract_text_exception_handling(self, ocr_processor, mock_file):
        """Test exception handling in extract_text."""
        with patch.object(ocr_processor, "_validate_file", side_effect=Exception("Unexpected error")):
            result = ocr_processor.extract_text(mock_file)

            assert result is None


class TestExtractTextWithMetadata:
    """Test text extraction with metadata functionality."""

    def test_extract_text_with_metadata_success(self, ocr_processor, mock_file):
        """Test successful text extraction with metadata."""
        expected_text = "This is extracted text from the document."

        mock_result = MagicMock()
        mock_result.content = expected_text
        mock_result.pages = [MagicMock(), MagicMock()]  # 2 pages
        mock_result.languages = [MagicMock(locale="en"), MagicMock(locale="es")]

        with patch.object(ocr_processor, "_validate_file", return_value=True):
            with patch.object(ocr_processor, "_perform_ocr_with_retry", return_value=mock_result):
                result = ocr_processor.extract_text_with_metadata(mock_file)

                assert result is not None
                assert result["text"] == expected_text
                assert result["page_count"] == 2
                assert result["word_count"] == len(expected_text.split())
                assert result["character_count"] == len(expected_text)
                assert result["languages"] == ["en", "es"]
                assert "processing_time" in result
                assert "file_size_bytes" in result
                assert result["file_size_bytes"] > 0

    def test_extract_text_with_metadata_empty_text(self, ocr_processor, mock_file):
        """Test metadata extraction with empty text."""
        mock_result = MagicMock()
        mock_result.content = ""
        mock_result.pages = []
        mock_result.languages = []

        with patch.object(ocr_processor, "_validate_file", return_value=True):
            with patch.object(ocr_processor, "_perform_ocr_with_retry", return_value=mock_result):
                result = ocr_processor.extract_text_with_metadata(mock_file)

                assert result is not None
                assert result["text"] == ""
                assert result["page_count"] == 0
                assert result["word_count"] == 0
                assert result["character_count"] == 0
                assert result["languages"] == []

    def test_extract_text_with_metadata_none_content(self, ocr_processor, mock_file):
        """Test metadata extraction with None content."""
        mock_result = MagicMock()
        mock_result.content = None
        mock_result.pages = [MagicMock()]
        mock_result.languages = []

        with patch.object(ocr_processor, "_validate_file", return_value=True):
            with patch.object(ocr_processor, "_perform_ocr_with_retry", return_value=mock_result):
                result = ocr_processor.extract_text_with_metadata(mock_file)

                assert result is not None
                assert result["text"] == ""
                assert result["word_count"] == 0

    def test_extract_text_with_metadata_validation_failure(self, ocr_processor, mock_file):
        """Test metadata extraction fails when file validation fails."""
        with patch.object(ocr_processor, "_validate_file", return_value=False):
            result = ocr_processor.extract_text_with_metadata(mock_file)

            assert result is None

    def test_extract_text_with_metadata_ocr_failure(self, ocr_processor, mock_file):
        """Test metadata extraction fails when OCR fails."""
        with patch.object(ocr_processor, "_validate_file", return_value=True):
            with patch.object(ocr_processor, "_perform_ocr_with_retry", return_value=None):
                result = ocr_processor.extract_text_with_metadata(mock_file)

                assert result is None

    def test_extract_text_with_metadata_language_logging(self, ocr_processor, mock_file):
        """Test that detected languages are logged."""
        mock_result = MagicMock()
        mock_result.content = "Test text"
        mock_result.pages = [MagicMock()]
        mock_result.languages = [MagicMock(locale="en"), MagicMock(locale="fr")]

        with patch.object(ocr_processor, "_validate_file", return_value=True):
            with patch.object(ocr_processor, "_perform_ocr_with_retry", return_value=mock_result):
                with patch("src.second_brain_ocr.ocr.logger") as mock_logger:
                    result = ocr_processor.extract_text_with_metadata(mock_file)

                    assert result is not None
                    assert result["languages"] == ["en", "fr"]
                    # Check that languages are logged
                    debug_calls = [
                        call for call in mock_logger.debug.call_args_list if "Detected languages" in str(call)
                    ]
                    assert len(debug_calls) > 0


class TestHealthCheck:
    """Test health check functionality."""

    def test_health_check_success(self, ocr_processor):
        """Test successful health check."""
        result = ocr_processor.health_check()
        assert result is True

    def test_health_check_with_exception(self, ocr_processor):
        """Test health check handles exceptions."""
        with patch("src.second_brain_ocr.ocr.logger.debug", side_effect=Exception("Test error")):
            result = ocr_processor.health_check()
            assert result is False


class TestLoggingIntegration:
    """Test logging integration."""

    def test_logger_initialization(self):
        """Test that logger is properly initialized from Config."""
        # Test that when we create a logger, it uses the right module name
        with patch("src.second_brain_ocr.config.Config.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # This should trigger logger creation
            from src.second_brain_ocr.config import Config

            result_logger = Config.get_logger("src.second_brain_ocr.ocr")

            mock_get_logger.assert_called_once_with("src.second_brain_ocr.ocr")
            assert result_logger == mock_logger

    def test_initialization_logging(self):
        """Test that initialization is logged."""
        with patch("src.second_brain_ocr.ocr.logger") as mock_logger:
            OCRProcessor("https://test.com", "key")

            mock_logger.info.assert_called_with("OCR processor initialized with endpoint: %s", "https://test.com")
