"""Essential tests for configuration management."""

from src.second_brain_ocr.config import Config


def test_config_validation_catches_missing_fields(monkeypatch, tmp_path):
    """Test that config validation catches missing Azure credentials."""
    monkeypatch.setattr(Config, "AZURE_DOC_INTELLIGENCE_ENDPOINT", "")
    monkeypatch.setattr(Config, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(Config, "AZURE_SEARCH_ENDPOINT", "")
    monkeypatch.setattr(Config, "STATE_FILE", tmp_path / "state.json")

    errors = Config.validate()
    assert len(errors) > 0
    assert any("AZURE" in error for error in errors)
