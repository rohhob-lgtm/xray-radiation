"""AI Chat Workspace — upload, folder-tree preservation, and ownership isolation."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth
from api.db.base import SessionLocal
from api.db.models import User

USER_A = {"id": "ws-test-user-a", "username": "a@example.com", "name": "User A"}
USER_B = {"id": "ws-test-user-b", "username": "b@example.com", "name": "User B"}


def _ensure_user(u: dict) -> None:
    s = SessionLocal()
    try:
        if not s.get(User, u["id"]):
            s.add(User(id=u["id"], username=u["username"], name=u["name"]))
            s.commit()
    finally:
        s.close()


@pytest.fixture
def client():
    _ensure_user(USER_A)
    _ensure_user(USER_B)
    app.dependency_overrides[require_auth] = lambda: USER_A
    return TestClient(app)


def _create_workspace(client, name="Test Workspace") -> str:
    resp = client.post("/api/workspaces", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_single_file_upload(client):
    ws_id = _create_workspace(client)
    resp = client.post(
        f"/api/workspaces/{ws_id}/upload",
        files=[("files", ("notes.txt", io.BytesIO(b"hello workspace"), "text/plain"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["uploaded"]) == 1
    assert body["uploaded"][0]["relative_path"] == "notes.txt"
    assert body["processing"]["total"] == 1
    assert body["workspace"]["total_files"] == 1


def test_multiple_file_upload(client):
    ws_id = _create_workspace(client)
    resp = client.post(
        f"/api/workspaces/{ws_id}/upload",
        files=[
            ("files", ("a.txt", io.BytesIO(b"file a"), "text/plain")),
            ("files", ("b.txt", io.BytesIO(b"file b"), "text/plain")),
            ("files", ("c.md", io.BytesIO(b"# heading"), "text/markdown")),
        ],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["uploaded"]) == 3
    assert body["workspace"]["total_files"] == 3


def test_nested_folder_upload_preserves_paths(client):
    ws_id = _create_workspace(client)
    resp = client.post(
        f"/api/workspaces/{ws_id}/upload-folder",
        data={
            "relative_paths": [
                "Manuals/Operator/intro.txt",
                "Manuals/Engineer/deep_dive.txt",
                "readme.txt",
            ]
        },
        files=[
            ("files", ("intro.txt", io.BytesIO(b"intro"), "text/plain")),
            ("files", ("deep_dive.txt", io.BytesIO(b"deep"), "text/plain")),
            ("files", ("readme.txt", io.BytesIO(b"root readme"), "text/plain")),
        ],
    )
    assert resp.status_code == 200, resp.text
    paths = sorted(f["relative_path"] for f in resp.json()["uploaded"])
    assert paths == ["Manuals/Engineer/deep_dive.txt", "Manuals/Operator/intro.txt", "readme.txt"]

    tree_resp = client.get(f"/api/workspaces/{ws_id}/tree")
    assert tree_resp.status_code == 200
    tree = tree_resp.json()["tree"]
    assert "Manuals" in tree
    assert "Operator" in tree["Manuals"]["children"]
    assert "readme.txt" in tree


def test_duplicate_filenames_different_folders(client):
    ws_id = _create_workspace(client)
    resp = client.post(
        f"/api/workspaces/{ws_id}/upload",
        data={"relative_paths": ["FolderA/spec.txt", "FolderB/spec.txt"]},
        files=[
            ("files", ("spec.txt", io.BytesIO(b"spec A"), "text/plain")),
            ("files", ("spec.txt", io.BytesIO(b"spec B"), "text/plain")),
        ],
    )
    assert resp.status_code == 200, resp.text
    uploaded = resp.json()["uploaded"]
    assert len(uploaded) == 2
    paths = {f["relative_path"] for f in uploaded}
    assert paths == {"FolderA/spec.txt", "FolderB/spec.txt"}


def test_path_traversal_rejected(client):
    ws_id = _create_workspace(client)
    resp = client.post(
        f"/api/workspaces/{ws_id}/upload",
        data={"relative_paths": ["../../etc/passwd"]},
        files=[("files", ("passwd", io.BytesIO(b"evil"), "text/plain"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["uploaded"]) == 0
    assert len(body["upload_errors"]) == 1


def test_executable_upload_rejected(client):
    ws_id = _create_workspace(client)
    resp = client.post(
        f"/api/workspaces/{ws_id}/upload",
        files=[("files", ("payload.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["uploaded"]) == 0
    assert "not allowed" in body["upload_errors"][0]


def test_unsupported_file_type_still_recorded(client):
    ws_id = _create_workspace(client)
    resp = client.post(
        f"/api/workspaces/{ws_id}/upload",
        files=[("files", ("model.glb", io.BytesIO(b"\x00\x01\x02"), "application/octet-stream"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["uploaded"]) == 1  # stored, just not parsed
    files_resp = client.get(f"/api/workspaces/{ws_id}/files")
    statuses = [f["parse_status"] for f in files_resp.json()]
    assert "unsupported" in statuses


def test_workspace_ownership_isolation(client):
    ws_id = _create_workspace(client)

    # Switch the auth override to a different user and attempt to read User A's workspace.
    app.dependency_overrides[require_auth] = lambda: USER_B
    other_client = TestClient(app)
    resp = other_client.get(f"/api/workspaces/{ws_id}")
    assert resp.status_code == 404

    resp2 = other_client.get(f"/api/workspaces/{ws_id}/files")
    assert resp2.status_code == 404

    resp3 = other_client.delete(f"/api/workspaces/{ws_id}")
    assert resp3.status_code == 404

    # Restore for any subsequent tests in this session.
    app.dependency_overrides[require_auth] = lambda: USER_A
