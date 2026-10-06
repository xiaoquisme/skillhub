"""Tests for the marketplace admin API (U4)."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from skillhub.main import app
from skillhub.api import deps
from skillhub.auth import create_token, hash_password
from skillhub.config import AppConfig, StorageConfig
from skillhub.database import Database

git = shutil.which("git")
needs_git = pytest.mark.skipif(git is None, reason="git not installed")


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def env(tmp_path):
    config = AppConfig(
        storage=StorageConfig(
            data_dir=tmp_path / "data",
            skills_dir=tmp_path / "skills",
        ),
    )
    db = Database(config.storage.data_dir / "skillhub.db")
    await db.connect()
    deps._config = config
    deps._db = db

    admin = await db.create_user(
        username="admin", password_hash=hash_password("p"), role="admin"
    )
    viewer = await db.create_user(
        username="viewer", password_hash=hash_password("p"), role="viewer"
    )
    tokens = {
        "admin": create_token(admin["id"], "admin"),
        "viewer": create_token(viewer["id"], "viewer"),
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, tokens, db, tmp_path

    await db.close()
    deps._db = None
    deps._config = None


def make_upstream_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "upstream"
    skill_dir = repo / "plugins" / "p" / "skills" / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hello\ndescription: greets\n---\nbody\n"
    )
    (repo / ".claude-plugin").mkdir()
    (repo / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "upstream-market",
                "owner": {"name": "t"},
                "plugins": [{"name": "p", "source": "./plugins/p", "version": "1.0.0"}],
            }
        )
    )
    for cmd in (
        ["init", "-q", "-b", "main"],
        ["add", "."],
        ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
    ):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.mark.asyncio
async def test_viewer_forbidden_on_mutations(env):
    client, tokens, db, _ = env
    headers = auth_headers(tokens["viewer"])
    body = {"name": "s", "location": "https://example.com/a.git"}

    assert (await client.post("/api/marketplaces", json=body, headers=headers)).status_code == 403
    assert (await client.post("/api/marketplaces/x/sync", headers=headers)).status_code == 403
    assert (await client.delete("/api/marketplaces/x", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_create_list_get_round_trip(env):
    client, tokens, db, _ = env
    headers = auth_headers(tokens["admin"])

    resp = await client.post(
        "/api/marketplaces",
        json={
            "name": "team",
            "location": "https://example.com/team.git",
            "source_ref": "main",
            "sync_interval_minutes": 30,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "team"
    assert body["imported_skill_count"] == 0
    assert body["last_synced_at"] is None

    listed = await client.get("/api/marketplaces", headers=headers)
    assert [s["name"] for s in listed.json()] == ["team"]

    fetched = await client.get(f"/api/marketplaces/{body['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["source_ref"] == "main"


@pytest.mark.asyncio
async def test_duplicate_name_returns_409(env):
    client, tokens, db, _ = env
    headers = auth_headers(tokens["admin"])
    body = {"name": "dup", "location": "https://example.com/a.git"}

    assert (await client.post("/api/marketplaces", json=body, headers=headers)).status_code == 201
    assert (await client.post("/api/marketplaces", json=body, headers=headers)).status_code == 409


@pytest.mark.asyncio
async def test_invalid_location_rejected_before_fetch(env):
    client, tokens, db, _ = env
    headers = auth_headers(tokens["admin"])

    resp = await client.post(
        "/api/marketplaces",
        json={"name": "bad", "location": "/srv/some/dir"},
        headers=headers,
    )
    assert resp.status_code in (400, 422)


@needs_git
@pytest.mark.asyncio
async def test_sync_imports_from_file_git_repo(env):
    client, tokens, db, tmp_path = env
    headers = auth_headers(tokens["admin"])
    repo = make_upstream_repo(tmp_path)

    created = await client.post(
        "/api/marketplaces",
        json={"name": "local", "location": f"file://{repo}"},
        headers=headers,
    )
    source_id = created.json()["id"]

    resp = await client.post(f"/api/marketplaces/{source_id}/sync", headers=headers)
    assert resp.status_code == 200
    report = resp.json()
    assert report["added"] == ["hello"]
    assert report["errors"] == []

    skills = await client.get(f"/api/marketplaces/{source_id}/skills", headers=headers)
    assert [s["name"] for s in skills.json()] == ["hello"]
    assert skills.json()[0]["upstream_status"] == "active"

    detail = await client.get(f"/api/skills/{skills.json()[0]['id']}", headers=headers)
    assert detail.json()["upstream"]["source"] == "local"
    assert detail.json()["upstream"]["version"] == "1.0.0"


@needs_git
@pytest.mark.asyncio
async def test_delete_removes_source_and_imported_skills(env):
    client, tokens, db, tmp_path = env
    headers = auth_headers(tokens["admin"])
    repo = make_upstream_repo(tmp_path)

    created = await client.post(
        "/api/marketplaces",
        json={"name": "local", "location": f"file://{repo}"},
        headers=headers,
    )
    source_id = created.json()["id"]
    await client.post(f"/api/marketplaces/{source_id}/sync", headers=headers)

    resp = await client.delete(f"/api/marketplaces/{source_id}", headers=headers)
    assert resp.status_code in (200, 204)

    assert (await client.get(f"/api/marketplaces/{source_id}", headers=headers)).status_code == 404
    listed = await client.get("/api/skills", headers=headers)
    assert listed.json() == []


@needs_git
@pytest.mark.asyncio
async def test_sync_failure_surfaces_last_error(env):
    client, tokens, db, tmp_path = env
    headers = auth_headers(tokens["admin"])

    created = await client.post(
        "/api/marketplaces",
        json={"name": "broken", "location": f"file://{tmp_path}/nope"},
        headers=headers,
    )
    source_id = created.json()["id"]

    resp = await client.post(f"/api/marketplaces/{source_id}/sync", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["errors"]

    fetched = await client.get(f"/api/marketplaces/{source_id}", headers=headers)
    assert fetched.json()["last_error"]


@needs_git
@pytest.mark.asyncio
async def test_interval_task_picks_up_post_startup_source(env):
    """A source created after startup with interval > 0 is synced by one tick."""
    from skillhub.api.marketplaces import sync_due_sources
    from skillhub.api.deps import get_storage as _gs

    client, tokens, db, tmp_path = env
    headers = auth_headers(tokens["admin"])
    repo = make_upstream_repo(tmp_path)
    storage = await _gs(deps._config)

    await client.post(
        "/api/marketplaces",
        json={
            "name": "late",
            "location": f"file://{repo}",
            "sync_interval_minutes": 1,
        },
        headers=headers,
    )

    assert await sync_due_sources(db, storage) == 1
    skills = await client.get("/api/skills", headers=headers)
    assert [s["name"] for s in skills.json()] == ["hello"]
