"""Tests for the marketplace sync and import engine (U3)."""

import pytest
import pytest_asyncio

from skillhub.database import Database
from skillhub.marketplace.models import ParseResult, UpstreamSkill
from skillhub.marketplace.sync import sync_source
from skillhub.storage import SkillStorage


@pytest_asyncio.fixture
async def env(tmp_path):
    db = Database(tmp_path / "db" / "test.db")
    await db.connect()
    storage = SkillStorage(tmp_path / "skills")
    yield db, storage
    await db.close()


def make_skill(name: str, path: str, body: str = "body v1", **kw) -> UpstreamSkill:
    return UpstreamSkill(
        name=name,
        description="d",
        path=path,
        plugin=kw.get("plugin", "p"),
        version=kw.get("version", "1.0.0"),
        files={"SKILL.md": f"---\nname: {name}\ndescription: d\n---\n{body}\n".encode()},
    )


@pytest.mark.asyncio
async def test_fresh_sync_adds_skills_and_provenance(env):
    db, storage = env
    source = await db.create_marketplace_source(
        name="src", location="https://example.com/m.git"
    )
    result = ParseResult(
        skills=[
            make_skill("alpha", "plugins/p/skills/alpha"),
            make_skill("beta", "plugins/p/skills/beta"),
        ]
    )

    report = await sync_source(db, storage, source, result, revision="rev1")

    assert report.added == ["alpha", "beta"]
    assert report.updated == []
    alpha = await db.get_skill_by_upstream(source["id"], "plugins/p/skills/alpha")
    assert alpha is not None
    assert alpha["upstream_status"] == "active"
    assert alpha["upstream_revision"] == "rev1"
    assert alpha["imported_hash"]
    assert storage.read_bundle_files(alpha["id"], None)["SKILL.md"]


@pytest.mark.asyncio
async def test_resync_updates_changed_skill_in_place(env):
    db, storage = env
    source = await db.create_marketplace_source(
        name="src", location="https://example.com/m.git"
    )
    first = ParseResult(skills=[make_skill("alpha", "p/a")])
    await sync_source(db, storage, source, first, revision="rev1")
    before = await db.get_skill_by_upstream(source["id"], "p/a")
    await db.increment_download_count(before["id"])

    second = ParseResult(skills=[make_skill("alpha", "p/a", body="body v2")])
    report = await sync_source(db, storage, source, second, revision="rev2")

    assert report.updated == ["alpha"]
    assert report.unchanged == []
    after = await db.get_skill_by_upstream(source["id"], "p/a")
    assert after["id"] == before["id"]
    assert after["download_count"] == 1
    assert b"body v2" in storage.read_bundle_files(after["id"], None)["SKILL.md"]


@pytest.mark.asyncio
async def test_resync_reports_unchanged_and_adds_new(env):
    db, storage = env
    source = await db.create_marketplace_source(
        name="src", location="https://example.com/m.git"
    )
    await sync_source(
        db, storage, source, ParseResult(skills=[make_skill("alpha", "p/a")]), "rev1"
    )

    report = await sync_source(
        db,
        storage,
        source,
        ParseResult(
            skills=[make_skill("alpha", "p/a"), make_skill("beta", "p/b")]
        ),
        revision="rev2",
    )

    assert report.unchanged == ["alpha"]
    assert report.added == ["beta"]


@pytest.mark.asyncio
async def test_removed_upstream_skill_flagged_not_deleted(env):
    db, storage = env
    source = await db.create_marketplace_source(
        name="src", location="https://example.com/m.git"
    )
    await sync_source(
        db,
        storage,
        source,
        ParseResult(skills=[make_skill("alpha", "p/a"), make_skill("beta", "p/b")]),
        "rev1",
    )

    report = await sync_source(
        db, storage, source, ParseResult(skills=[make_skill("alpha", "p/a")]), "rev2"
    )

    assert report.missing == ["beta"]
    beta = await db.get_skill_by_upstream(source["id"], "p/b")
    assert beta is not None
    assert beta["upstream_status"] == "missing-upstream"
    assert storage.read_bundle_files(beta["id"], None)["SKILL.md"]


@pytest.mark.asyncio
async def test_name_collision_with_local_skill_skipped(env):
    db, storage = env
    await db.create_skill(name="deploy")
    source = await db.create_marketplace_source(
        name="src", location="https://example.com/m.git"
    )

    report = await sync_source(
        db,
        storage,
        source,
        ParseResult(skills=[make_skill("deploy", "p/deploy")]),
        "rev1",
    )

    assert report.skipped_conflicts == ["deploy"]
    local = await db.get_skill_by_name("deploy")
    assert local.get("marketplace_source_id") is None
    assert await db.get_skill_by_upstream(source["id"], "p/deploy") is None


@pytest.mark.asyncio
async def test_same_source_different_upstream_path_is_conflict(env):
    db, storage = env
    source = await db.create_marketplace_source(
        name="src", location="https://example.com/m.git"
    )
    await sync_source(
        db, storage, source, ParseResult(skills=[make_skill("deploy", "p/one")]), "rev1"
    )

    report = await sync_source(
        db, storage, source, ParseResult(skills=[make_skill("deploy", "p/two")]), "rev2"
    )

    assert report.skipped_conflicts == ["deploy"]


@pytest.mark.asyncio
async def test_locally_edited_skill_skipped_not_overwritten(env):
    db, storage = env
    source = await db.create_marketplace_source(
        name="src", location="https://example.com/m.git"
    )
    await sync_source(
        db, storage, source, ParseResult(skills=[make_skill("alpha", "p/a")]), "rev1"
    )
    skill = await db.get_skill_by_upstream(source["id"], "p/a")

    # Local edit: publish different content through the storage publication path
    async with storage.lock("skill:" + skill["id"]):
        with storage.publication_files(
            skill["id"], [("SKILL.md", b"---\nname: alpha\ndescription: d\n---\nlocal edit\n", "text/markdown")], None
        ):
            await db.update_skill(skill["id"], description="locally edited")

    report = await sync_source(
        db,
        storage,
        source,
        ParseResult(skills=[make_skill("alpha", "p/a", body="body v2")]),
        "rev2",
    )

    assert report.skipped_local_edits == ["alpha"]
    assert b"local edit" in storage.read_bundle_files(skill["id"], None)["SKILL.md"]


@pytest.mark.asyncio
async def test_error_recorded_and_no_writes(env):
    db, storage = env
    source = await db.create_marketplace_source(
        name="src", location="https://example.com/m.git"
    )
    await sync_source(
        db, storage, source, ParseResult(skills=[make_skill("alpha", "p/a")]), "rev1"
    )

    await sync_source(db, storage, source, None, "rev2", error="fetch failed")

    updated = await db.get_marketplace_source(source["id"])
    assert updated["last_error"] == "fetch failed"
    alpha = await db.get_skill_by_upstream(source["id"], "p/a")
    assert alpha["upstream_status"] == "active"
