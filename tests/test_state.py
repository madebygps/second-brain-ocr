"""Essential tests for state management."""

import pytest

from src.second_brain_ocr.state import StateManager


@pytest.fixture
def temp_state_file(tmp_path):
    return tmp_path / "test_state.json"


def test_state_tracks_processed_files(temp_state_file):
    """Test that state manager tracks which files have been processed."""
    manager = StateManager(temp_state_file)
    manager.mark_processed("/test/file.jpg")

    assert manager.is_processed("/test/file.jpg")
    assert not manager.is_processed("/test/other.jpg")


def test_state_persists_across_restarts(temp_state_file):
    """Test that processed files are saved and loaded correctly."""
    manager1 = StateManager(temp_state_file)
    manager1.mark_processed("/test/file.jpg")

    # Create new instance - should load existing state
    manager2 = StateManager(temp_state_file)
    assert manager2.is_processed("/test/file.jpg")
