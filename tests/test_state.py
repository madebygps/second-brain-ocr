"""Tests for state management."""

import json

import pytest

from src.second_brain_ocr.state import StateManager


@pytest.fixture
def temp_state_file(tmp_path):
    return tmp_path / "test_state.json"


def test_state_manager_initialization_no_file(temp_state_file):
    manager = StateManager(temp_state_file)
    assert len(manager.processed_files) == 0
    assert temp_state_file.parent.exists()


def test_state_manager_loads_existing_state(temp_state_file):
    test_data = {"processed_files": ["/path/to/file1.jpg", "/path/to/file2.png"], "last_updated": "2025-01-01T00:00:00"}
    temp_state_file.parent.mkdir(parents=True, exist_ok=True)
    with temp_state_file.open("w") as f:
        json.dump(test_data, f)

    manager = StateManager(temp_state_file)
    assert len(manager.processed_files) == 2
    assert "/path/to/file1.jpg" in manager.processed_files


def test_is_processed(temp_state_file):
    manager = StateManager(temp_state_file)
    manager.mark_processed("/test/file.jpg")

    assert manager.is_processed("/test/file.jpg")
    assert not manager.is_processed("/test/other.jpg")


def test_mark_processed_saves_state(temp_state_file):
    manager = StateManager(temp_state_file)
    manager.mark_processed("/test/file.jpg")

    assert temp_state_file.exists()
    with temp_state_file.open() as f:
        data = json.load(f)
    assert "/test/file.jpg" in data["processed_files"]
    assert "last_updated" in data


def test_mark_batch_processed(temp_state_file):
    manager = StateManager(temp_state_file)
    files = ["/test/file1.jpg", "/test/file2.jpg", "/test/file3.jpg"]
    manager.mark_batch_processed(files)

    assert len(manager.processed_files) == 3
    for file in files:
        assert manager.is_processed(file)


def test_state_file_sorted(temp_state_file):
    manager = StateManager(temp_state_file)
    manager.mark_batch_processed(["/z.jpg", "/a.jpg", "/m.jpg"])

    with temp_state_file.open() as f:
        data = json.load(f)
    assert data["processed_files"] == ["/a.jpg", "/m.jpg", "/z.jpg"]


def test_corrupted_state_file_handled(temp_state_file):
    temp_state_file.parent.mkdir(parents=True, exist_ok=True)
    with temp_state_file.open("w") as f:
        f.write("invalid json {{{")

    manager = StateManager(temp_state_file)
    assert len(manager.processed_files) == 0


def test_unicode_whitespace_normalization(temp_state_file):
    """Test that unicode whitespace characters are normalized."""
    manager = StateManager(temp_state_file)

    # Non-breaking space (\u202f) and regular space should be treated the same
    path_with_nbsp = "/test/file\u202fwith\u202fspaces.jpg"
    path_with_regular_space = "/test/file with spaces.jpg"

    # Mark file with non-breaking space
    manager.mark_processed(path_with_nbsp)

    # Should be found with regular spaces (normalized)
    assert manager.is_processed(path_with_regular_space)

    # And vice versa
    manager2 = StateManager(temp_state_file)
    manager2.mark_processed(path_with_regular_space)
    assert manager2.is_processed(path_with_nbsp)
