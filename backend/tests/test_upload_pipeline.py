"""Targeted tests for the translation upload pipeline.

These tests verify:
  - small PPTX upload succeeds and creates a project
  - oversized uploads are rejected with HTTP 400
  - empty uploads are rejected with HTTP 400
  - backend returns a clear status/message for every failure
"""
import os
import sys

# Make the backend package importable from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth
from api.db.base import SessionLocal
from api.db.models import User


def _fake_user() -> dict:
    return {
        "id": "test-upload-user",
        "email": "test-upload@example.com",
        "name": "Test Upload",
    }


app.dependency_overrides[require_auth] = _fake_user

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SMALL_PPTX = os.path.join(FIXTURES, "test_basic.pptx")
EMPTY_FILE = os.path.join(FIXTURES, "empty.txt")


def _ensure_empty_file() -> None:
    with open(EMPTY_FILE, "w") as fh:
        fh.write("")


def _ensure_test_user() -> None:
    """Create the fake user in the DB so the FK constraint on projects is satisfied."""
    s = SessionLocal()
    try:
        if not s.get(User, "test-upload-user"):
            s.add(User(
                id="test-upload-user",
                username="test-upload@example.com",
                name="Test Upload",
            ))
            s.commit()
    finally:
        s.close()


@pytest.fixture
def client():
    _ensure_test_user()
    return TestClient(app)


def test_upload_small_pptx(client):
    """A normal small PPTX should upload, create a project, and return its id."""
    assert os.path.exists(SMALL_PPTX), f"Missing fixture: {SMALL_PPTX}"
    with open(SMALL_PPTX, "rb") as fh:
        resp = client.post(
            "/api/translation/projects",
            data={
                "name": "Upload Pipeline Test",
                "source_lang": "en",
                "target_lang": "ar",
                "style": "technical",
                "keep_english_terms": "false",
                "transliterate_names": "true",
                "provider_name": "auto",
                "layout_mode": "original",
                "layout_options": "{}",
            },
            files={
                "file": (
                    "test_basic.pptx",
                    fh,
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
            },
        )
    assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "id" in body and body["id"]
    assert body["source_file_type"] == "pptx"
    assert body["status"] == "ready"
    assert body["source_lang"] == "en"
    assert body["target_lang"] == "ar"


def test_upload_rejects_oversized(client):
    """The backend must reject uploads that exceed the configured size limit."""
    from api.utils import cost_guard

    original_limit = cost_guard.max_file_size_bytes
    cost_guard.max_file_size_bytes = lambda: 1  # 1 byte limit for the test
    try:
        with open(SMALL_PPTX, "rb") as fh:
            resp = client.post(
                "/api/translation/projects",
                data={
                    "name": "Too big",
                    "source_lang": "en",
                    "target_lang": "ar",
                },
                files={
                    "file": (
                        "test_basic.pptx",
                        fh,
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    )
                },
            )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "too large" in detail.lower(), f"Expected size rejection detail, got: {detail}"
    finally:
        cost_guard.max_file_size_bytes = original_limit


def test_upload_rejects_empty_file(client):
    """An empty file must be rejected with a clear message."""
    _ensure_empty_file()
    with open(EMPTY_FILE, "rb") as fh:
        resp = client.post(
            "/api/translation/projects",
            data={
                "name": "Empty",
                "source_lang": "en",
                "target_lang": "ar",
            },
            files={"file": ("empty.txt", fh, "text/plain")},
        )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", "")
    assert "empty" in detail.lower(), f"Expected empty-file detail, got: {detail}"
