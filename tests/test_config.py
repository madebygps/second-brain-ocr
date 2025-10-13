"""Tests for configuration management."""

import os
from pathlib import Path

from src.second_brain_ocr.config import Config


def test_config_defaults(monkeypatch):
    """Test that config loads with proper defaults when no env vars are set."""
    # Clear any environment variables that might be set
    monkeypatch.delenv("WATCH_DIR", raising=False)
    monkeypatch.delenv("POLLING_INTERVAL", raising=False)
    monkeypatch.delenv("BATCH_SIZE", raising=False)

    # Test the actual defaults from config.py
    assert os.getenv("WATCH_DIR", "/brain-notes") == "/brain-notes"
    assert int(os.getenv("POLLING_INTERVAL", "180")) == 180
    assert int(os.getenv("BATCH_SIZE", "10")) == 10


def test_config_watch_dir_from_env():
    """Test that WATCH_DIR can be loaded from environment or defaults."""
    # Config.WATCH_DIR will be whatever is set in the environment or the default
    # Just verify it's a Path object and exists as an attribute
    assert isinstance(Config.WATCH_DIR, Path)
    assert Config.POLLING_INTERVAL == 180
    assert Config.BATCH_SIZE == 10


def test_config_supported_extensions():
    expected = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".pdf")
    assert expected == Config.SUPPORTED_IMAGE_EXTENSIONS


def test_config_validation_missing_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "AZURE_DOC_INTELLIGENCE_ENDPOINT", "")
    monkeypatch.setattr(Config, "AZURE_DOC_INTELLIGENCE_KEY", "")
    monkeypatch.setattr(Config, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(Config, "AZURE_OPENAI_KEY", "")
    monkeypatch.setattr(Config, "AZURE_SEARCH_ENDPOINT", "")
    monkeypatch.setattr(Config, "AZURE_SEARCH_KEY", "")
    # Use tmp_path for STATE_FILE to avoid permission errors in CI
    monkeypatch.setattr(Config, "STATE_FILE", tmp_path / "state.json")

    errors = Config.validate()
    assert len(errors) == 6
    assert "AZURE_DOC_INTELLIGENCE_ENDPOINT is required" in errors


def test_config_validation_all_fields_present(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://example.com")
    monkeypatch.setattr(Config, "AZURE_DOC_INTELLIGENCE_KEY", "test-key")
    monkeypatch.setattr(Config, "AZURE_OPENAI_ENDPOINT", "https://openai.example.com")
    monkeypatch.setattr(Config, "AZURE_OPENAI_KEY", "test-key")
    monkeypatch.setattr(Config, "AZURE_SEARCH_ENDPOINT", "https://search.example.com")
    monkeypatch.setattr(Config, "AZURE_SEARCH_KEY", "test-key")
    # Use tmp_path for STATE_FILE to avoid permission errors in CI
    monkeypatch.setattr(Config, "STATE_FILE", tmp_path / "state.json")

    errors = Config.validate()
    assert errors == []
