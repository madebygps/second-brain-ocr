"""Tests for configuration management."""

from pathlib import Path

from src.second_brain_ocr.config import Config


def test_config_defaults():
    # Note: WATCH_DIR is loaded from .env file, which may override the default
    assert Path("brain-notes") == Config.WATCH_DIR
    assert Config.POLLING_INTERVAL == 180
    assert Config.BATCH_SIZE == 10


def test_config_supported_extensions():
    expected = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".pdf")
    assert expected == Config.SUPPORTED_IMAGE_EXTENSIONS


def test_config_validation_missing_fields(monkeypatch):
    monkeypatch.setattr(Config, "AZURE_DOC_INTELLIGENCE_ENDPOINT", "")
    monkeypatch.setattr(Config, "AZURE_DOC_INTELLIGENCE_KEY", "")
    monkeypatch.setattr(Config, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(Config, "AZURE_OPENAI_KEY", "")
    monkeypatch.setattr(Config, "AZURE_SEARCH_ENDPOINT", "")
    monkeypatch.setattr(Config, "AZURE_SEARCH_KEY", "")

    errors = Config.validate()
    assert len(errors) == 6
    assert "AZURE_DOC_INTELLIGENCE_ENDPOINT is required" in errors


def test_config_validation_all_fields_present(monkeypatch):
    monkeypatch.setattr(Config, "AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://example.com")
    monkeypatch.setattr(Config, "AZURE_DOC_INTELLIGENCE_KEY", "test-key")
    monkeypatch.setattr(Config, "AZURE_OPENAI_ENDPOINT", "https://openai.example.com")
    monkeypatch.setattr(Config, "AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setattr(Config, "AZURE_SEARCH_ENDPOINT", "https://search.example.com")
    monkeypatch.setattr(Config, "AZURE_SEARCH_KEY", "test-key")

    errors = Config.validate()
    assert errors == []
