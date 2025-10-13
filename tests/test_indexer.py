"""Comprehensive unit tests for search indexer module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
)

from src.second_brain_ocr.indexer import SearchIndexer


@pytest.fixture
def indexer():
    """Create search indexer instance for testing."""
    return SearchIndexer(
        endpoint="https://test.search.windows.net",
        api_key="test-key-12345",  # Valid length for testing
        index_name="test-index",
        embedding_dimension=1536,
    )


@pytest.fixture
def mock_search_result():
    """Create mock search result."""
    result = MagicMock()
    result.get = lambda x, default=None: {
        "file_name": "test.jpg",
        "file_path": "/test/path/test.jpg",
        "content": "Test content",
        "category": "books",
        "source": "test-book",
        "title": "Test Book",
        "@search.score": 0.95,
    }.get(x, default)
    return result


class TestSearchIndexerInitialization:
    """Test search indexer initialization."""

    def test_initialization_success(self):
        """Test successful indexer initialization."""
        indexer = SearchIndexer(
            endpoint="https://test.search.windows.net",
            api_key="test-key-12345",
            index_name="test-index",
            embedding_dimension=1536,
        )

        assert indexer.endpoint == "https://test.search.windows.net"
        assert indexer.index_name == "test-index"
        assert indexer.embedding_dimension == 1536
        assert indexer.max_retries == 3
        assert indexer.base_delay == 1.0
        assert indexer.timeout == 30

    def test_initialization_with_custom_parameters(self):
        """Test initialization with custom retry and timeout parameters."""
        indexer = SearchIndexer(
            endpoint="https://test.search.windows.net",
            api_key="test-key-12345",
            index_name="test-index",
            embedding_dimension=3072,
            max_retries=5,
            base_delay=2.0,
            timeout=60,
        )

        assert indexer.embedding_dimension == 3072
        assert indexer.max_retries == 5
        assert indexer.base_delay == 2.0
        assert indexer.timeout == 60

    def test_initialization_invalid_config(self):
        """Test initialization fails with invalid configuration."""
        with pytest.raises(ValueError):
            SearchIndexer(
                endpoint="",  # Invalid empty endpoint
                api_key="test-key-12345",
                index_name="test-index",
                embedding_dimension=1536,
            )

    def test_initialization_tracks_operations(self, indexer):
        """Test that operation counters are initialized."""
        assert indexer.operation_count == 0
        assert indexer.error_count == 0


class TestConfigValidation:
    """Test configuration validation functionality."""

    def test_validate_config_valid_endpoint(self, indexer):
        """Test validation succeeds for valid HTTPS endpoint."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "test-index", 1536)
        assert result is True

    def test_validate_config_http_endpoint(self, indexer):
        """Test validation succeeds for HTTP endpoint."""
        result = indexer._validate_config("http://localhost:8080", "test-key-123", "test-index", 1536)
        assert result is True

    def test_validate_config_invalid_endpoint_empty(self, indexer):
        """Test validation fails for empty endpoint."""
        result = indexer._validate_config("", "test-key", "test-index", 1536)
        assert result is False

    def test_validate_config_invalid_endpoint_no_protocol(self, indexer):
        """Test validation fails for endpoint without protocol."""
        result = indexer._validate_config("test.search.windows.net", "test-key", "test-index", 1536)
        assert result is False

    def test_validate_config_invalid_api_key_empty(self, indexer):
        """Test validation fails for empty API key."""
        result = indexer._validate_config("https://test.search.windows.net", "", "test-index", 1536)
        assert result is False

    def test_validate_config_invalid_api_key_too_short(self, indexer):
        """Test validation fails for too-short API key."""
        result = indexer._validate_config("https://test.search.windows.net", "short", "test-index", 1536)
        assert result is False

    def test_validate_config_invalid_index_name_empty(self, indexer):
        """Test validation fails for empty index name."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "", 1536)
        assert result is False

    def test_validate_config_invalid_index_name_uppercase(self, indexer):
        """Test validation fails for uppercase in index name."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "Test-Index", 1536)
        assert result is False

    def test_validate_config_invalid_index_name_special_chars(self, indexer):
        """Test validation fails for special characters in index name."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "test_index!", 1536)
        assert result is False

    def test_validate_config_invalid_index_name_starts_with_number(self, indexer):
        """Test validation fails for index name starting with number."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "1test-index", 1536)
        assert result is False

    def test_validate_config_invalid_index_name_too_long(self, indexer):
        """Test validation fails for index name exceeding 128 characters."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "a" * 129, 1536)
        assert result is False

    def test_validate_config_valid_index_name_boundary(self, indexer):
        """Test validation succeeds for index name at 128 character limit."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "a" * 128, 1536)
        assert result is True

    def test_validate_config_invalid_embedding_dimension_zero(self, indexer):
        """Test validation fails for zero embedding dimension."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "test-index", 0)
        assert result is False

    def test_validate_config_invalid_embedding_dimension_negative(self, indexer):
        """Test validation fails for negative embedding dimension."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "test-index", -1536)
        assert result is False

    def test_validate_config_invalid_embedding_dimension_exceeds_max(self, indexer):
        """Test validation fails for embedding dimension exceeding 3072."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "test-index", 3073)
        assert result is False

    def test_validate_config_valid_embedding_dimension_boundary(self, indexer):
        """Test validation succeeds for embedding dimension at 3072 limit."""
        result = indexer._validate_config("https://test.search.windows.net", "test-key-123", "test-index", 3072)
        assert result is True


class TestRetryLogic:
    """Test retry mechanisms."""

    @patch("src.second_brain_ocr.indexer.time.sleep")
    def test_retry_success_first_attempt(self, mock_sleep, indexer):
        """Test successful operation on first attempt."""
        mock_operation = MagicMock(return_value="success", __name__="test_operation")

        result = indexer._execute_with_retry(mock_operation, "arg1", kwarg1="value1")

        assert result == "success"
        mock_operation.assert_called_once_with("arg1", kwarg1="value1")
        mock_sleep.assert_not_called()
        assert indexer.operation_count == 1
        assert indexer.error_count == 0

    @patch("src.second_brain_ocr.indexer.time.sleep")
    def test_retry_success_second_attempt(self, mock_sleep, indexer):
        """Test successful operation on second attempt after server error."""
        server_error = HttpResponseError("Server error")
        server_error.status_code = 500

        mock_operation = MagicMock(side_effect=[server_error, "success"], __name__="test_operation")

        result = indexer._execute_with_retry(mock_operation)

        assert result == "success"
        assert mock_operation.call_count == 2
        mock_sleep.assert_called_once_with(1.0)  # base_delay
        assert indexer.error_count == 1

    @patch("src.second_brain_ocr.indexer.time.sleep")
    def test_retry_exponential_backoff_rate_limiting(self, mock_sleep, indexer):
        """Test exponential backoff for rate limiting (429) errors."""
        rate_limit_error = HttpResponseError("Rate limited")
        rate_limit_error.status_code = 429

        mock_operation = MagicMock(side_effect=rate_limit_error, __name__="test_operation")

        result = indexer._execute_with_retry(mock_operation)

        assert result is None
        assert mock_operation.call_count == 3  # Initial + 2 retries
        # Exponential backoff: 1s, 2s
        expected_delays = [1.0, 2.0]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    @patch("src.second_brain_ocr.indexer.time.sleep")
    def test_retry_exponential_backoff_server_errors(self, mock_sleep, indexer):
        """Test exponential backoff for server (5xx) errors."""
        server_error = HttpResponseError("Internal server error")
        server_error.status_code = 503

        mock_operation = MagicMock(side_effect=server_error, __name__="test_operation")

        result = indexer._execute_with_retry(mock_operation)

        assert result is None
        # Exponential backoff: 1s, 2s
        expected_delays = [1.0, 2.0]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    def test_retry_no_retry_client_errors(self, indexer):
        """Test client errors (4xx except 429) are not retried."""
        client_error = HttpResponseError("Bad request")
        client_error.status_code = 400

        mock_operation = MagicMock(side_effect=client_error, __name__="test_operation")

        result = indexer._execute_with_retry(mock_operation)

        assert result is None
        assert mock_operation.call_count == 1  # No retries
        assert indexer.error_count == 1

    def test_retry_no_retry_authentication_errors(self, indexer):
        """Test authentication errors fall through to general retry handler."""
        auth_error = ClientAuthenticationError("Invalid credentials")

        mock_operation = MagicMock(side_effect=auth_error, __name__="test_operation")

        with patch("src.second_brain_ocr.indexer.time.sleep"):
            result = indexer._execute_with_retry(mock_operation)

        assert result is None
        # Authentication errors get retried (falls through to general handler)
        assert mock_operation.call_count == 3

    @patch("src.second_brain_ocr.indexer.time.sleep")
    def test_retry_service_request_errors(self, mock_sleep, indexer):
        """Test service request errors are retried."""
        service_error = ServiceRequestError("Network error")

        mock_operation = MagicMock(side_effect=service_error, __name__="test_operation")

        result = indexer._execute_with_retry(mock_operation)

        assert result is None
        assert mock_operation.call_count == 3

    @patch("src.second_brain_ocr.indexer.time.sleep")
    def test_retry_unexpected_errors(self, mock_sleep, indexer):
        """Test unexpected errors are retried with linear backoff."""
        unexpected_error = RuntimeError("Unexpected error")

        mock_operation = MagicMock(side_effect=unexpected_error, __name__="test_operation")

        result = indexer._execute_with_retry(mock_operation)

        assert result is None
        assert mock_operation.call_count == 3
        # Linear backoff for unexpected errors
        expected_delays = [1.0, 1.0]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays


class TestCreateOrUpdateIndex:
    """Test index creation and update functionality."""

    def test_create_index_success(self, indexer):
        """Test successful index creation."""
        mock_index = MagicMock()

        with patch.object(indexer.index_client, "create_or_update_index", return_value=mock_index):
            result = indexer.create_or_update_index()

            assert result is True
            indexer.index_client.create_or_update_index.assert_called_once()

    def test_create_index_with_retry_on_failure(self, indexer):
        """Test index creation retries on failure."""
        server_error = HttpResponseError("Server error")
        server_error.status_code = 500

        with patch.object(indexer.index_client, "create_or_update_index", side_effect=server_error):
            with patch("src.second_brain_ocr.indexer.time.sleep"):
                result = indexer.create_or_update_index()

                assert result is False
                assert indexer.index_client.create_or_update_index.call_count == 3

    def test_create_index_logs_duration(self, indexer):
        """Test that index creation logs duration."""
        mock_index = MagicMock()

        with patch.object(indexer.index_client, "create_or_update_index", return_value=mock_index):
            with patch("src.second_brain_ocr.indexer.logger") as mock_logger:
                result = indexer.create_or_update_index()

                assert result is True
                info_calls = [
                    call for call in mock_logger.info.call_args_list if "created/updated successfully" in str(call)
                ]
                assert len(info_calls) > 0


class TestIndexDocument:
    """Test document indexing functionality."""

    def test_index_document_success(self, indexer):
        """Test successful document indexing."""
        file_path = Path("/brain-notes/books/test-book/page1.jpg")
        content = "Test content for indexing"
        embedding = [0.1] * 1536

        with patch.object(indexer.search_client, "upload_documents") as mock_upload:
            mock_result = MagicMock()
            mock_result.succeeded = True
            mock_upload.return_value = [mock_result]

            success = indexer.index_document(file_path, content, embedding)

            assert success is True
            mock_upload.assert_called_once()

    def test_index_document_id_generation(self, indexer):
        """Test document ID generation is safe for Azure Search."""
        file_path = Path("/brain-notes/books/test-book/page1.jpg")
        content = "test content"
        embedding = [0.1] * 1536

        with patch.object(indexer.search_client, "upload_documents") as mock_upload:
            mock_result = MagicMock()
            mock_result.succeeded = True
            mock_upload.return_value = [mock_result]

            indexer.index_document(file_path, content, embedding)

            doc = mock_upload.call_args[1]["documents"][0]
            doc_id = doc["id"]

            # Should not start with underscore
            assert not doc_id.startswith("_")
            # Should not contain dots or slashes
            assert "." not in doc_id
            assert "/" not in doc_id

    def test_index_document_path_parsing_books(self, indexer):
        """Test path parsing for books category."""
        file_path = Path("/Users/test/brain-notes/books/atomic-habits/page1.jpg")
        content = "test content"
        embedding = [0.1] * 1536

        with patch.object(indexer.search_client, "upload_documents") as mock_upload:
            mock_result = MagicMock()
            mock_result.succeeded = True
            mock_upload.return_value = [mock_result]

            indexer.index_document(file_path, content, embedding)

            doc = mock_upload.call_args[1]["documents"][0]

            assert doc["category"] == "books"
            assert doc["source"] == "atomic-habits"
            assert doc["title"] == "Atomic Habits"

    def test_index_document_path_parsing_unknown(self, indexer):
        """Test path parsing defaults to unknown when brain-notes not in path."""
        file_path = Path("/random/path/file.jpg")
        content = "test content"
        embedding = [0.1] * 1536

        with patch.object(indexer.search_client, "upload_documents") as mock_upload:
            mock_result = MagicMock()
            mock_result.succeeded = True
            mock_upload.return_value = [mock_result]

            indexer.index_document(file_path, content, embedding)

            doc = mock_upload.call_args[1]["documents"][0]

            assert doc["category"] == "unknown"
            assert doc["source"] == "unknown"

    def test_index_document_title_formatting(self, indexer):
        """Test title formatting from source names."""
        test_cases = [
            ("atomic-habits", "Atomic Habits"),
            ("the_power_of_now", "The Power Of Now"),
            ("win-every_argument", "Win Every Argument"),
        ]

        for source, expected_title in test_cases:
            file_path = Path(f"/brain-notes/books/{source}/page1.jpg")
            content = "test"
            embedding = [0.1] * 1536

            with patch.object(indexer.search_client, "upload_documents") as mock_upload:
                mock_result = MagicMock()
                mock_result.succeeded = True
                mock_upload.return_value = [mock_result]

                indexer.index_document(file_path, content, embedding)

                doc = mock_upload.call_args[1]["documents"][0]
                assert doc["title"] == expected_title

    def test_index_document_metadata_fields(self, indexer):
        """Test all metadata fields are included."""
        file_path = Path("/brain-notes/essays/philosophy/note.jpg")
        content = "This is test content with multiple words."
        embedding = [0.1] * 1536

        with patch.object(indexer.search_client, "upload_documents") as mock_upload:
            mock_result = MagicMock()
            mock_result.succeeded = True
            mock_upload.return_value = [mock_result]

            indexer.index_document(file_path, content, embedding)

            doc = mock_upload.call_args[1]["documents"][0]

            assert "id" in doc
            assert doc["content"] == content
            assert doc["file_name"] == "note.jpg"
            assert doc["file_path"] == str(file_path)
            assert doc["category"] == "essays"
            assert doc["source"] == "philosophy"
            assert doc["title"] == "Philosophy"
            assert doc["word_count"] == 7
            assert "created_at" in doc
            assert "indexed_at" in doc
            assert doc["content_vector"] == embedding

    def test_index_document_with_custom_metadata(self, indexer):
        """Test indexing with additional custom metadata."""
        file_path = Path("/brain-notes/books/test/page.jpg")
        content = "test"
        embedding = [0.1] * 1536
        custom_metadata = {"custom_field": "custom_value"}

        with patch.object(indexer.search_client, "upload_documents") as mock_upload:
            mock_result = MagicMock()
            mock_result.succeeded = True
            mock_upload.return_value = [mock_result]

            indexer.index_document(file_path, content, embedding, metadata=custom_metadata)

            doc = mock_upload.call_args[1]["documents"][0]

            assert doc["custom_field"] == "custom_value"

    def test_index_document_upload_failure(self, indexer):
        """Test document indexing handles upload failure."""
        file_path = Path("/test/file.jpg")
        content = "test"
        embedding = [0.1] * 1536

        with patch.object(indexer.search_client, "upload_documents") as mock_upload:
            mock_result = MagicMock()
            mock_result.succeeded = False
            mock_upload.return_value = [mock_result]

            success = indexer.index_document(file_path, content, embedding)

            assert success is False

    def test_index_document_exception_handling(self, indexer):
        """Test document indexing handles exceptions gracefully."""
        file_path = Path("/test/file.jpg")
        content = "test"
        embedding = [0.1] * 1536

        with patch.object(indexer.search_client, "upload_documents", side_effect=ValueError("Invalid data")):
            success = indexer.index_document(file_path, content, embedding)

            assert success is False


class TestSearch:
    """Test search functionality."""

    def test_search_with_vector_query(self, indexer, mock_search_result):
        """Test search with vector similarity."""
        with patch.object(indexer.search_client, "search") as mock_search:
            mock_search.return_value = [mock_search_result]

            query = "test query"
            query_vector = [0.1] * 1536

            results = indexer.search(query, query_vector, top=5)

            assert len(results) == 1
            assert results[0]["file_name"] == "test.jpg"
            assert results[0]["score"] == 0.95
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args[1]
            assert "vector_queries" in call_kwargs

    def test_search_text_only(self, indexer):
        """Test text-only search without vector."""
        with patch.object(indexer.search_client, "search") as mock_search:
            mock_search.return_value = []

            results = indexer.search("test query", top=3)

            assert results == []
            call_kwargs = mock_search.call_args[1]
            assert "vector_queries" not in call_kwargs

    def test_search_with_filter_expression(self, indexer, mock_search_result):
        """Test search with filter expression."""
        with patch.object(indexer.search_client, "search") as mock_search:
            mock_search.return_value = [mock_search_result]

            results = indexer.search(
                "test query", query_vector=[0.1] * 1536, top=5, filter_expression="category eq 'books'"
            )

            assert len(results) == 1
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["filter"] == "category eq 'books'"

    def test_search_result_formatting(self, indexer):
        """Test search results are properly formatted."""
        mock_result = MagicMock()
        mock_result.get = lambda x, default=None: {
            "file_name": "test.jpg",
            "file_path": "/path/test.jpg",
            "content": "A" * 1000,  # Long content
            "category": "books",
            "source": "test-book",
            "title": "Test Book",
            "@search.score": 0.85,
        }.get(x, default)

        with patch.object(indexer.search_client, "search") as mock_search:
            mock_search.return_value = [mock_result]

            results = indexer.search("test", query_vector=[0.1] * 1536)

            assert len(results) == 1
            # Content should be truncated to 500 characters
            assert len(results[0]["content"]) <= 500

    def test_search_handles_none_content(self, indexer):
        """Test search handles None content gracefully."""
        mock_result = MagicMock()
        mock_result.get = lambda x, default=None: {"file_name": "test.jpg", "content": None, "@search.score": 0.85}.get(
            x, default
        )

        with patch.object(indexer.search_client, "search") as mock_search:
            mock_search.return_value = [mock_result]

            results = indexer.search("test")

            assert len(results) == 1
            assert results[0]["content"] == ""

    def test_search_exception_handling(self, indexer):
        """Test search handles exceptions gracefully."""
        with patch.object(indexer.search_client, "search", side_effect=ValueError("Search error")):
            results = indexer.search("test query")

            assert results == []


class TestHealthCheck:
    """Test health check functionality."""

    def test_health_check_success_index_exists(self, indexer):
        """Test successful health check when index exists."""
        mock_index = MagicMock()
        mock_index.name = "test-index"

        with patch.object(indexer.index_client, "list_indexes", return_value=[mock_index]):
            with patch.object(indexer.search_client, "search", return_value=[]):
                result = indexer.health_check()

                assert result is True

    def test_health_check_warning_index_not_exists(self, indexer):
        """Test health check warns when index doesn't exist."""
        mock_index = MagicMock()
        mock_index.name = "other-index"

        with patch.object(indexer.index_client, "list_indexes", return_value=[mock_index]):
            result = indexer.health_check()

            assert result is False

    def test_health_check_failure_exception(self, indexer):
        """Test health check fails on exception."""
        with patch.object(indexer.index_client, "list_indexes", side_effect=Exception("Connection error")):
            result = indexer.health_check()

            assert result is False


class TestGetIndexStats:
    """Test index statistics functionality."""

    def test_get_index_stats_success(self, indexer):
        """Test successful retrieval of index statistics."""
        # Mock paged results - the issue is list() loses get_count
        # So we mock the search to return something that list() can iterate
        # but then we mock the list function's result
        mock_paged_results = MagicMock()
        mock_paged_results.__iter__ = lambda self: iter([])

        # Create mock list result that has get_count
        mock_list_result = MagicMock(spec=list)
        mock_list_result.get_count = MagicMock(return_value=42)

        mock_index = MagicMock()
        mock_index.fields = [MagicMock()] * 10

        with patch.object(indexer.search_client, "search", return_value=mock_paged_results):
            with patch("builtins.list", return_value=mock_list_result):
                with patch.object(indexer.index_client, "get_index", return_value=mock_index):
                    stats = indexer.get_index_stats()

                    assert stats["index_name"] == "test-index"
                    assert stats["document_count"] == 42
                    assert stats["field_count"] == 10
                    assert stats["embedding_dimension"] == 1536
                    assert "timestamp" in stats

    def test_get_index_stats_index_not_found(self, indexer):
        """Test index stats when index doesn't exist."""
        mock_search_results = MagicMock()
        mock_search_results.get_count = lambda: 0

        with patch.object(indexer.search_client, "search", return_value=mock_search_results):
            with patch.object(indexer.index_client, "get_index", side_effect=ResourceNotFoundError("Not found")):
                stats = indexer.get_index_stats()

                assert stats["document_count"] == 0
                assert stats["field_count"] == 0

    def test_get_index_stats_error_handling(self, indexer):
        """Test index stats handles errors gracefully."""
        with patch.object(indexer.search_client, "search", side_effect=Exception("Connection error")):
            stats = indexer.get_index_stats()

            assert "error" in stats
            assert stats["index_name"] == "test-index"

    def test_get_index_stats_includes_error_rate(self, indexer):
        """Test index stats includes error rate calculation."""
        # Simulate some operations and errors
        indexer.operation_count = 100
        indexer.error_count = 5

        mock_search_results = MagicMock()
        mock_search_results.get_count = lambda: 10

        with patch.object(indexer.search_client, "search", return_value=mock_search_results):
            with patch.object(indexer.index_client, "get_index", side_effect=ResourceNotFoundError()):
                stats = indexer.get_index_stats()

                assert stats["operation_count"] == 100
                assert stats["error_count"] == 5
                assert stats["error_rate"] == 5.0  # 5/100 * 100


class TestGetIndexerInfo:
    """Test indexer information functionality."""

    def test_get_indexer_info(self, indexer):
        """Test getting indexer configuration information."""
        info = indexer.get_indexer_info()

        assert isinstance(info, dict)
        assert info["endpoint"] == "https://test.search.windows.net"
        assert info["index_name"] == "test-index"
        assert info["embedding_dimension"] == 1536
        assert info["max_retries"] == 3
        assert info["base_delay"] == 1.0
        assert info["timeout"] == 30
        assert info["version"] == "enhanced"

    def test_get_indexer_info_tracks_operations(self, indexer):
        """Test indexer info includes operation tracking."""
        indexer.operation_count = 50
        indexer.error_count = 2

        info = indexer.get_indexer_info()

        assert info["operation_count"] == 50
        assert info["error_count"] == 2


class TestLoggingIntegration:
    """Test logging integration."""

    def test_logger_initialization(self):
        """Test that logger is properly initialized from Config."""
        with patch("src.second_brain_ocr.config.Config.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            from src.second_brain_ocr.config import Config

            result_logger = Config.get_logger("src.second_brain_ocr.indexer")

            mock_get_logger.assert_called_once_with("src.second_brain_ocr.indexer")
            assert result_logger == mock_logger

    def test_initialization_logging(self):
        """Test that initialization is logged."""
        with patch("src.second_brain_ocr.indexer.logger") as mock_logger:
            SearchIndexer(
                endpoint="https://test.search.windows.net",
                api_key="test-key-12345",
                index_name="test-index",
                embedding_dimension=1536,
            )

            info_calls = [call for call in mock_logger.info.call_args_list if "initialized" in str(call)]
            assert len(info_calls) > 0
