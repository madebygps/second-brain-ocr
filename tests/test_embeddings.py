"""Tests for embeddings generation."""

from unittest.mock import MagicMock, patch

import pytest

from src.second_brain_ocr.embeddings import EmbeddingGenerator


@pytest.fixture
def embedding_gen():
    return EmbeddingGenerator(
        endpoint="https://test.openai.azure.com", api_key="test-key", deployment_name="text-embedding-3-large"
    )


def test_chunk_text_short_text(embedding_gen):
    short_text = "This is a short text that doesn't need chunking."
    chunks = embedding_gen.chunk_text(short_text, max_tokens=100)

    assert len(chunks) == 1
    assert chunks[0] == short_text


def test_chunk_text_long_text(embedding_gen):
    long_text = "word " * 10000
    chunks = embedding_gen.chunk_text(long_text, max_tokens=1000, overlap=50)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 1000 * 4


def test_chunk_text_sentence_boundaries(embedding_gen):
    text = "First sentence. " * 1000
    chunks = embedding_gen.chunk_text(text, max_tokens=500, overlap=50)

    assert len(chunks) > 1
    for chunk in chunks:
        if chunk != chunks[-1]:
            assert chunk.endswith(". ") or chunk.endswith(".")


def test_chunk_text_with_overlap(embedding_gen):
    text = "A" * 5000
    chunks = embedding_gen.chunk_text(text, max_tokens=500, overlap=100)

    assert len(chunks) >= 2


def test_generate_embedding_empty_text(embedding_gen):
    assert embedding_gen.generate_embedding("") is None
    assert embedding_gen.generate_embedding("   ") is None


@patch("src.second_brain_ocr.embeddings.AzureOpenAI")
def test_generate_embedding_success(mock_openai, embedding_gen):
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 3072)]
    embedding_gen.client.embeddings.create = MagicMock(return_value=mock_response)

    result = embedding_gen.generate_embedding("test text")

    assert result == [0.1] * 3072
    embedding_gen.client.embeddings.create.assert_called_once()


@patch("src.second_brain_ocr.embeddings.AzureOpenAI")
def test_generate_embeddings_batch(mock_openai, embedding_gen):
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 3072)]
    embedding_gen.client.embeddings.create = MagicMock(return_value=mock_response)

    texts = ["text1", "text2", "text3"]
    results = embedding_gen.generate_embeddings_batch(texts)

    assert len(results) == 3
    assert all(r == [0.1] * 3072 for r in results)
    assert embedding_gen.client.embeddings.create.call_count == 3


@patch("src.second_brain_ocr.embeddings.AzureOpenAI")
def test_generate_embedding_error_handling(mock_openai, embedding_gen):
    embedding_gen.client.embeddings.create = MagicMock(side_effect=ValueError("API error"))

    result = embedding_gen.generate_embedding("test text")

    assert result is None
