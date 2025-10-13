"""Integration tests for the full OCR pipeline."""

from unittest.mock import MagicMock, patch

import pytest

from src.second_brain_ocr.main import SecondBrainOCR


@pytest.fixture
def temp_brain_notes(tmp_path):
    brain_notes = tmp_path / "brain-notes"
    brain_notes.mkdir()

    books_dir = brain_notes / "books" / "test-book"
    books_dir.mkdir(parents=True)
    (books_dir / "page1.jpg").write_bytes(b"fake image data")

    return brain_notes


@pytest.fixture
def mock_azure_services(monkeypatch, tmp_path):
    monkeypatch.setattr("src.second_brain_ocr.config.Config.WATCH_DIR", tmp_path / "brain-notes")
    monkeypatch.setattr("src.second_brain_ocr.config.Config.STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr("src.second_brain_ocr.config.Config.AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://test.com")
    monkeypatch.setattr("src.second_brain_ocr.config.Config.AZURE_DOC_INTELLIGENCE_KEY", "test-key-12345")
    monkeypatch.setattr("src.second_brain_ocr.config.Config.AZURE_OPENAI_ENDPOINT", "https://test.com")
    monkeypatch.setattr("src.second_brain_ocr.config.Config.AZURE_OPENAI_KEY", "test-key-12345")
    monkeypatch.setattr("src.second_brain_ocr.config.Config.AZURE_SEARCH_ENDPOINT", "https://test.com")
    monkeypatch.setattr("src.second_brain_ocr.config.Config.AZURE_SEARCH_KEY", "test-key-12345")


@patch("src.second_brain_ocr.ocr.DocumentIntelligenceClient")
@patch("src.second_brain_ocr.embeddings.AzureOpenAI")
@patch("src.second_brain_ocr.indexer.SearchIndexClient")
@patch("src.second_brain_ocr.indexer.SearchClient")
def test_full_pipeline_integration(
    mock_search_client, mock_index_client, mock_openai, mock_doc_intel, temp_brain_notes, mock_azure_services
):
    mock_doc_result = MagicMock()
    mock_doc_result.content = "This is extracted text from the document."
    mock_doc_result.pages = [MagicMock()]
    mock_doc_result.languages = [MagicMock(locale="en")]

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_doc_result
    mock_doc_intel.return_value.begin_analyze_document.return_value = mock_poller

    mock_embedding_response = MagicMock()
    mock_embedding_response.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_openai.return_value.embeddings.create.return_value = mock_embedding_response

    mock_upload_result = MagicMock()
    mock_upload_result.succeeded = True
    mock_search_client.return_value.upload_documents.return_value = [mock_upload_result]

    mock_index_client.return_value.create_or_update_index.return_value = None

    with patch.object(SecondBrainOCR, "start", return_value=None):
        app = SecondBrainOCR()

        # Reset mocks after initialization/health checks
        mock_openai.return_value.embeddings.create.reset_mock()
        mock_doc_intel.return_value.begin_analyze_document.reset_mock()
        mock_search_client.return_value.upload_documents.reset_mock()

        test_file = temp_brain_notes / "books" / "test-book" / "page1.jpg"
        app.process_file(test_file)

        assert app.state_manager.is_processed(str(test_file))
        mock_doc_intel.return_value.begin_analyze_document.assert_called_once()
        mock_openai.return_value.embeddings.create.assert_called_once()
        mock_search_client.return_value.upload_documents.assert_called_once()


@patch("src.second_brain_ocr.ocr.DocumentIntelligenceClient")
@patch("src.second_brain_ocr.embeddings.AzureOpenAI")
@patch("src.second_brain_ocr.indexer.SearchIndexClient")
@patch("src.second_brain_ocr.indexer.SearchClient")
def test_pipeline_handles_ocr_failure(
    mock_search_client, mock_index_client, mock_openai, mock_doc_intel, temp_brain_notes, mock_azure_services
):
    mock_poller = MagicMock()
    mock_poller.result.return_value = MagicMock(content=None, pages=[], languages=[])
    mock_doc_intel.return_value.begin_analyze_document.return_value = mock_poller

    mock_index_client.return_value.create_or_update_index.return_value = None

    with patch.object(SecondBrainOCR, "start", return_value=None):
        app = SecondBrainOCR()

        # Reset mocks after initialization/health checks
        mock_openai.return_value.embeddings.create.reset_mock()
        mock_doc_intel.return_value.begin_analyze_document.reset_mock()
        mock_search_client.return_value.upload_documents.reset_mock()

        test_file = temp_brain_notes / "books" / "test-book" / "page1.jpg"
        app.process_file(test_file)

        assert not app.state_manager.is_processed(str(test_file))
        mock_openai.return_value.embeddings.create.assert_not_called()
        mock_search_client.return_value.upload_documents.assert_not_called()


@patch("src.second_brain_ocr.ocr.DocumentIntelligenceClient")
@patch("src.second_brain_ocr.embeddings.AzureOpenAI")
@patch("src.second_brain_ocr.indexer.SearchIndexClient")
@patch("src.second_brain_ocr.indexer.SearchClient")
def test_pipeline_handles_embedding_failure(
    mock_search_client, mock_index_client, mock_openai, mock_doc_intel, temp_brain_notes, mock_azure_services
):
    mock_doc_result = MagicMock()
    mock_doc_result.content = "This is extracted text."
    mock_doc_result.pages = [MagicMock()]
    mock_doc_result.languages = []

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_doc_result
    mock_doc_intel.return_value.begin_analyze_document.return_value = mock_poller

    mock_openai.return_value.embeddings.create.side_effect = ValueError("API Error")

    mock_index_client.return_value.create_or_update_index.return_value = None

    with patch.object(SecondBrainOCR, "start", return_value=None):
        app = SecondBrainOCR()

        test_file = temp_brain_notes / "books" / "test-book" / "page1.jpg"
        app.process_file(test_file)

        assert not app.state_manager.is_processed(str(test_file))
        mock_search_client.return_value.upload_documents.assert_not_called()


@patch("src.second_brain_ocr.ocr.DocumentIntelligenceClient")
@patch("src.second_brain_ocr.embeddings.AzureOpenAI")
@patch("src.second_brain_ocr.indexer.SearchIndexClient")
@patch("src.second_brain_ocr.indexer.SearchClient")
def test_pipeline_skips_already_processed_files(
    mock_search_client, mock_index_client, mock_openai, mock_doc_intel, temp_brain_notes, mock_azure_services
):
    mock_index_client.return_value.create_or_update_index.return_value = None

    with patch.object(SecondBrainOCR, "start", return_value=None):
        app = SecondBrainOCR()

        # Reset mocks after initialization/health checks
        mock_openai.return_value.embeddings.create.reset_mock()
        mock_doc_intel.return_value.begin_analyze_document.reset_mock()
        mock_search_client.return_value.upload_documents.reset_mock()

        test_file = temp_brain_notes / "books" / "test-book" / "page1.jpg"
        app.state_manager.mark_processed(str(test_file))

        app.process_file(test_file)

        mock_doc_intel.return_value.begin_analyze_document.assert_not_called()
        mock_openai.return_value.embeddings.create.assert_not_called()
        mock_search_client.return_value.upload_documents.assert_not_called()
