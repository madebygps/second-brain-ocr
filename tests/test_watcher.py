"""Tests for file watcher functionality."""

from unittest.mock import MagicMock

import pytest

from src.second_brain_ocr.watcher import scan_existing_files


@pytest.fixture
def temp_watch_dir(tmp_path):
    watch_dir = tmp_path / "brain-notes"
    watch_dir.mkdir()

    books_dir = watch_dir / "books" / "test-book"
    books_dir.mkdir(parents=True)

    (books_dir / "page1.jpg").touch()
    (books_dir / "page2.png").touch()
    (books_dir / "notes.txt").touch()

    articles_dir = watch_dir / "articles" / "test-article"
    articles_dir.mkdir(parents=True)
    (articles_dir / "highlight.jpg").touch()

    return watch_dir


def test_scan_existing_files_finds_images(temp_watch_dir):
    mock_state = MagicMock()
    mock_state.is_processed.return_value = False

    supported_exts = (".jpg", ".jpeg", ".png")
    files = scan_existing_files(temp_watch_dir, supported_exts, mock_state)

    assert len(files) == 3
    file_names = {f.name for f in files}
    assert "page1.jpg" in file_names
    assert "page2.png" in file_names
    assert "highlight.jpg" in file_names
    assert "notes.txt" not in file_names


def test_scan_existing_files_skips_processed(temp_watch_dir):
    mock_state = MagicMock()

    def is_processed(path):
        return "page1.jpg" in path

    mock_state.is_processed.side_effect = is_processed

    supported_exts = (".jpg", ".jpeg", ".png")
    files = scan_existing_files(temp_watch_dir, supported_exts, mock_state)

    assert len(files) == 2
    file_names = {f.name for f in files}
    assert "page1.jpg" not in file_names
    assert "page2.png" in file_names


def test_scan_existing_files_nonexistent_dir(tmp_path):
    mock_state = MagicMock()
    nonexistent = tmp_path / "does-not-exist"

    supported_exts = (".jpg", ".png")
    files = scan_existing_files(nonexistent, supported_exts, mock_state)

    assert files == []


def test_scan_existing_files_empty_dir(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    mock_state = MagicMock()
    mock_state.is_processed.return_value = False

    supported_exts = (".jpg", ".png")
    files = scan_existing_files(empty_dir, supported_exts, mock_state)

    assert files == []


def test_scan_existing_files_recursive(temp_watch_dir):
    nested = temp_watch_dir / "books" / "test-book" / "chapter1" / "section1"
    nested.mkdir(parents=True)
    (nested / "deep.jpg").touch()

    mock_state = MagicMock()
    mock_state.is_processed.return_value = False

    supported_exts = (".jpg",)
    files = scan_existing_files(temp_watch_dir, supported_exts, mock_state)

    file_names = {f.name for f in files}
    assert "deep.jpg" in file_names
