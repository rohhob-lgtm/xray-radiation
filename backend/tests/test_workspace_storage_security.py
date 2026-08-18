"""Path-traversal / zip-bomb / archive-safety unit tests (no HTTP layer)."""
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from api.utils import workspace_storage
from api.utils.archive_processor import extract_zip_safely
from api.config import settings


def test_sanitize_rejects_dotdot():
    with pytest.raises(workspace_storage.UnsafePathError):
        workspace_storage.sanitize_relative_path("../../etc/passwd")


def test_sanitize_rejects_absolute_posix():
    with pytest.raises(workspace_storage.UnsafePathError):
        workspace_storage.sanitize_relative_path("/etc/passwd")


def test_sanitize_rejects_absolute_windows():
    with pytest.raises(workspace_storage.UnsafePathError):
        workspace_storage.sanitize_relative_path("C:\\Windows\\System32\\evil.dll")


def test_sanitize_rejects_nul_byte():
    with pytest.raises(workspace_storage.UnsafePathError):
        workspace_storage.sanitize_relative_path("evil\x00.txt")


def test_sanitize_rejects_reserved_device_name():
    with pytest.raises(workspace_storage.UnsafePathError):
        workspace_storage.sanitize_relative_path("folder/CON.txt")


def test_sanitize_accepts_normal_nested_path():
    result = workspace_storage.sanitize_relative_path("Manuals/Operator/intro.txt")
    assert result == "Manuals/Operator/intro.txt"


def test_sanitize_normalizes_backslashes():
    result = workspace_storage.sanitize_relative_path("Manuals\\Operator\\intro.txt")
    assert result == "Manuals/Operator/intro.txt"


def test_extract_zip_rejects_path_traversal_entry():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "gotcha")
        zf.writestr("safe.txt", "fine")
    result = extract_zip_safely("test-zip-user", "test-zip-ws-traversal", buf.getvalue())
    safe_paths = [e.relative_path for e in result.entries]
    assert "safe.txt" in safe_paths
    assert not any(".." in e.relative_path for e in result.entries)
    assert any("evil.txt" in s["path"] for s in result.skipped)


def test_extract_zip_bomb_rejected(monkeypatch):
    # Craft a zip whose declared uncompressed size is far beyond a tiny cap.
    monkeypatch.setattr(settings, "max_zip_uncompressed_size_mb", 1)  # 1MB cap
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        huge = b"0" * (5 * 1024 * 1024)  # 5MB, compresses tiny but declares 5MB
        zf.writestr("bomb.bin", huge)
    result = extract_zip_safely("test-zip-user", "test-zip-ws-bomb", buf.getvalue())
    assert result.entries == []
    assert any("exceed" in s["reason"] for s in result.skipped)


def test_extract_zip_normal_entries():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Manuals/intro.txt", "intro text")
        zf.writestr("readme.md", "# hi")
    result = extract_zip_safely("test-zip-user", "test-zip-ws-normal", buf.getvalue())
    paths = sorted(e.relative_path for e in result.entries)
    assert paths == ["Manuals/intro.txt", "readme.md"]
    for e in result.entries:
        assert os.path.exists(e.storage_path)
