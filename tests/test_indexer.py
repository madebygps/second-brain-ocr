"""Tests for search indexer functionality."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.second_brain_ocr.indexer import SearchIndexer


@pytest.fixture
def indexer():
    return SearchIndexer(
        endpoint="https://test.search.windows.net",
        api_key="test-key",
        index_name="test-index",
        embedding_dimension=1536,
    )


def test_indexer_initialization(indexer):
    assert indexer.endpoint == "https://test.search.windows.net"
    assert indexer.index_name == "test-index"
    assert indexer.embedding_dimension == 1536


def test_document_id_generation_basic_path(indexer):
    file_path = Path("/brain-notes/books/test-book/page1.jpg")
    content = "test content"
    embedding = [0.1] * 1536

    with patch.object(indexer.search_client, "upload_documents") as mock_upload:
        mock_result = MagicMock()
        mock_result.succeeded = True
        mock_upload.return_value = [mock_result]

        success = indexer.index_document(file_path, content, embedding)

        assert success
        call_args = mock_upload.call_args[1]["documents"][0]
        doc_id = call_args["id"]

        assert not doc_id.startswith("_")
        assert "." not in doc_id
        assert "/" not in doc_id


def test_document_path_parsing(indexer):
    file_path = Path("/Users/test/brain-notes/books/win-every-argument/page1.jpg")
    content = "test content"
    embedding = [0.1] * 1536

    with patch.object(indexer.search_client, "upload_documents") as mock_upload:
        mock_result = MagicMock()
        mock_result.succeeded = True
        mock_upload.return_value = [mock_result]

        indexer.index_document(file_path, content, embedding)

        call_args = mock_upload.call_args[1]["documents"][0]

        assert call_args["category"] == "books"
        assert call_args["source"] == "win-every-argument"
        assert call_args["title"] == "Win Every Argument"


def test_title_formatting(indexer):
    test_cases = [
        ("win-every-argument", "Win Every Argument"),
        ("the_power_of_now", "The Power Of Now"),
        ("atomic-habits", "Atomic Habits"),
        ("how_to_win_friends-and-influence_people", "How To Win Friends And Influence People"),
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

            call_args = mock_upload.call_args[1]["documents"][0]
            assert call_args["title"] == expected_title


def test_document_metadata_fields(indexer):
    file_path = Path("/brain-notes/essays/test-essay/note.jpg")
    content = "This is test content for indexing."
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
        assert doc["category"] == "essays"
        assert doc["source"] == "test-essay"
        assert doc["word_count"] == 6
        assert "created_at" in doc
        assert "indexed_at" in doc
        assert doc["content_vector"] == embedding


def test_index_document_failure(indexer):
    file_path = Path("/test/file.jpg")
    content = "test"
    embedding = [0.1] * 1536

    with patch.object(indexer.search_client, "upload_documents") as mock_upload:
        mock_result = MagicMock()
        mock_result.succeeded = False
        mock_upload.return_value = [mock_result]

        success = indexer.index_document(file_path, content, embedding)

        assert not success


def test_search_with_vector(indexer):
    with patch.object(indexer.search_client, "search") as mock_search:
        mock_result = MagicMock()
        mock_result.get = lambda x, default="": "test_value" if x != "@search.score" else 0.95
        mock_search.return_value = [mock_result]

        query = "test query"
        query_vector = [0.1] * 1536

        results = indexer.search(query, query_vector, top=5)

        assert len(results) == 1
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args[1]
        assert "vector_queries" in call_kwargs


def test_search_text_only(indexer):
    with patch.object(indexer.search_client, "search") as mock_search:
        mock_search.return_value = []

        results = indexer.search("test query", top=3)

        assert results == []
        call_kwargs = mock_search.call_args[1]
        assert "vector_queries" not in call_kwargs
