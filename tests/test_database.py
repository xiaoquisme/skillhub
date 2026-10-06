"""Tests for database operations."""

import tempfile
from pathlib import Path
import pytest
import pytest_asyncio

from skillhub.database import Database

@pytest_asyncio.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        await database.connect()
        yield database
        await database.close()


@pytest.mark.asyncio
async def test_create_skill(db):
    """Test creating a skill."""
    skill = await db.create_skill(
        name="test-skill",
        display_name="Test Skill",
        description="A test skill",
        category="testing",
        tags=["python", "test"],
        author="tester",
    )
    assert skill["name"] == "test-skill"
    assert skill["display_name"] == "Test Skill"
    assert "id" in skill
    assert skill["download_count"] == 0


@pytest.mark.asyncio
async def test_get_skill(db):
    """Test getting a skill by ID."""
    created = await db.create_skill(name="get-me")
    fetched = await db.get_skill(created["id"])
    assert fetched is not None
    assert fetched["name"] == "get-me"


@pytest.mark.asyncio
async def test_get_skill_by_name(db):
    """Test getting a skill by name."""
    await db.create_skill(name="named-skill")
    found = await db.get_skill_by_name("named-skill")
    assert found is not None
    assert found["name"] == "named-skill"


@pytest.mark.asyncio
async def test_update_skill(db):
    """Test updating a skill."""
    created = await db.create_skill(name="update-me")
    updated = await db.update_skill(created["id"], description="Updated description")
    assert updated["description"] == "Updated description"


@pytest.mark.asyncio
async def test_delete_skill(db):
    """Test deleting a skill."""
    created = await db.create_skill(name="delete-me")
    result = await db.delete_skill(created["id"])
    assert result is True
    assert await db.get_skill(created["id"]) is None


@pytest.mark.asyncio
async def test_list_skills(db):
    """Test listing skills."""
    await db.create_skill(name="skill-1")
    await db.create_skill(name="skill-2")
    await db.create_skill(name="skill-3")

    skills = await db.list_skills()
    assert len(skills) == 3


@pytest.mark.asyncio
async def test_list_skills_with_query(db):
    """Test listing skills with search query."""
    await db.create_skill(name="python-tool", description="A Python tool")
    await db.create_skill(name="js-tool", description="A JavaScript tool")

    skills = await db.list_skills(query="python")
    assert len(skills) == 1
    assert skills[0]["name"] == "python-tool"


@pytest.mark.asyncio
async def test_list_skills_with_category(db):
    """Test listing skills with category filter."""
    await db.create_skill(name="skill-a", category="testing")
    await db.create_skill(name="skill-b", category="production")

    skills = await db.list_skills(category="testing")
    assert len(skills) == 1
    assert skills[0]["name"] == "skill-a"


@pytest.mark.asyncio
async def test_count_skills(db):
    """Test counting skills."""
    await db.create_skill(name="count-1")
    await db.create_skill(name="count-2")

    count = await db.count_skills()
    assert count == 2


@pytest.mark.asyncio
async def test_skill_files(db):
    """Test skill file operations."""
    skill = await db.create_skill(name="file-skill")

    await db.add_skill_file(skill["id"], "SKILL.md", "text/markdown", 100)
    await db.add_skill_file(skill["id"], "refs/api.md", "text/markdown", 50)

    files = await db.get_skill_files(skill["id"])
    assert len(files) == 2

    await db.delete_skill_files(skill["id"])
    files = await db.get_skill_files(skill["id"])
    assert len(files) == 0


@pytest.mark.asyncio
async def test_download_count_starts_at_zero(db):
    """Test that new skills start with download_count = 0."""
    skill = await db.create_skill(name="fresh-skill")
    fetched = await db.get_skill(skill["id"])
    assert fetched["download_count"] == 0


@pytest.mark.asyncio
async def test_increment_download_count(db):
    """Test that increment_download_count increases count by 1."""
    skill = await db.create_skill(name="counted-skill")
    await db.increment_download_count(skill["id"])

    fetched = await db.get_skill(skill["id"])
    assert fetched["download_count"] == 1


@pytest.mark.asyncio
async def test_increment_download_count_twice(db):
    """Test that incrementing twice yields count = 2."""
    skill = await db.create_skill(name="double-skill")
    await db.increment_download_count(skill["id"])
    await db.increment_download_count(skill["id"])

    fetched = await db.get_skill(skill["id"])
    assert fetched["download_count"] == 2


@pytest.mark.asyncio
async def test_increment_download_count_nonexistent_skill(db):
    """Test that incrementing a non-existent skill is a no-op."""
    # Should not raise an error
    await db.increment_download_count("nonexistent-id")
    # Verify no skill was created
    assert await db.get_skill("nonexistent-id") is None


@pytest.mark.asyncio
async def test_list_skills_sort_by_downloads(db):
    """Test listing skills sorted by download count."""
    skill_a = await db.create_skill(name="popular")
    skill_b = await db.create_skill(name="unpopular")

    # popular gets 5 downloads, unpopular gets 1
    for _ in range(5):
        await db.increment_download_count(skill_a["id"])
    await db.increment_download_count(skill_b["id"])

    skills = await db.list_skills(sort="download_count")
    assert skills[0]["name"] == "popular"
    assert skills[0]["download_count"] == 5
    assert skills[1]["name"] == "unpopular"
    assert skills[1]["download_count"] == 1


# --- Marketplace sources (U1) ---


@pytest.mark.asyncio
async def test_marketplace_source_round_trip(db):
    """Create, get-by-name, list, update, and delete a marketplace source."""
    created = await db.create_marketplace_source(
        name="team-marketplace",
        location="https://example.com/team/marketplace.git",
        source_ref="main",
        sync_interval_minutes=60,
    )
    assert created["name"] == "team-marketplace"
    assert created["location"] == "https://example.com/team/marketplace.git"
    assert created["source_ref"] == "main"
    assert created["sync_interval_minutes"] == 60
    assert created["enabled"] == 1
    assert created["last_synced_at"] is None

    by_name = await db.get_marketplace_source_by_name("team-marketplace")
    assert by_name["id"] == created["id"]

    listed = await db.list_marketplace_sources()
    assert [s["id"] for s in listed] == [created["id"]]

    updated = await db.update_marketplace_source(
        created["id"], source_ref="v2", sync_interval_minutes=0
    )
    assert updated["source_ref"] == "v2"
    assert updated["sync_interval_minutes"] == 0

    assert await db.delete_marketplace_source(created["id"]) is True
    assert await db.get_marketplace_source(created["id"]) is None


@pytest.mark.asyncio
async def test_marketplace_source_unique_name(db):
    """Duplicate source names are rejected at the database level."""
    await db.create_marketplace_source(name="dup", location="https://example.com/a.git")
    with pytest.raises(Exception):
        await db.create_marketplace_source(name="dup", location="https://example.com/b.git")


@pytest.mark.asyncio
async def test_provenance_columns_added_to_legacy_db(tmp_path):
    """Opening a legacy database adds provenance columns; old skills get NULL provenance."""
    import aiosqlite

    legacy = tmp_path / "legacy.db"
    conn = await aiosqlite.connect(str(legacy))
    await conn.executescript(
        """
        CREATE TABLE skills (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            display_name TEXT,
            description TEXT,
            category TEXT,
            tags TEXT,
            author TEXT,
            license TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_by TEXT,
            download_count INTEGER DEFAULT 0,
            project_id TEXT DEFAULT NULL,
            UNIQUE(name, project_id)
        );
        INSERT INTO skills (id, name) VALUES ('old-skill', 'legacy');
        """
    )
    await conn.commit()
    await conn.close()

    database = Database(legacy)
    await database.connect()
    try:
        skill = await database.get_skill("old-skill")
        assert skill["marketplace_source_id"] is None
        assert skill["upstream_path"] is None
        assert skill["upstream_status"] is None
        assert skill["imported_hash"] is None
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_get_skill_by_upstream(db):
    """Provenance lookup matches (marketplace_source_id, upstream_path), not name."""
    source = await db.create_marketplace_source(
        name="prov-src", location="https://example.com/p.git"
    )
    created = await db.create_skill(
        name="imported",
        marketplace_source_id=source["id"],
        upstream_path="plugins/a/skills/b",
        upstream_version="1.0.0",
        upstream_revision="abc123",
        upstream_status="active",
        imported_hash="hash-1",
    )
    found = await db.get_skill_by_upstream(source["id"], "plugins/a/skills/b")
    assert found["id"] == created["id"]

    # Same name with different provenance must not match
    assert await db.get_skill_by_upstream(source["id"], "other/path") is None
    other = await db.create_marketplace_source(
        name="prov-src-2", location="https://example.com/q.git"
    )
    assert await db.get_skill_by_upstream(other["id"], "plugins/a/skills/b") is None


@pytest.mark.asyncio
async def test_delete_skills_by_source(db):
    """delete_skills_by_source removes only that source's skills and their file rows."""
    source = await db.create_marketplace_source(
        name="del-src", location="https://example.com/d.git"
    )
    keep_source = await db.create_marketplace_source(
        name="keep-src", location="https://example.com/k.git"
    )
    mine = await db.create_skill(name="mine", marketplace_source_id=source["id"])
    theirs = await db.create_skill(name="theirs", marketplace_source_id=keep_source["id"])
    local = await db.create_skill(name="local")
    await db.add_skill_file(mine["id"], "SKILL.md")
    await db.add_skill_file(theirs["id"], "SKILL.md")

    removed = await db.delete_skills_by_source(source["id"])
    assert removed == 1
    assert await db.get_skill(mine["id"]) is None
    assert await db.get_skill_files(mine["id"]) == []
    assert await db.get_skill(theirs["id"]) is not None
    assert await db.get_skill(local["id"]) is not None


@pytest.mark.asyncio
async def test_touch_marketplace_sync(db):
    """touch_marketplace_sync records revision, report, error, and timestamp."""
    source = await db.create_marketplace_source(
        name="touch-src", location="https://example.com/t.git"
    )
    updated = await db.touch_marketplace_sync(
        source["id"],
        last_revision="rev1",
        last_sync_report='{"added": 1}',
        last_error=None,
    )
    assert updated["last_revision"] == "rev1"
    assert updated["last_sync_report"] == '{"added": 1}'
    assert updated["last_error"] is None
    assert updated["last_synced_at"] is not None

    failed = await db.touch_marketplace_sync(
        source["id"],
        last_revision="rev1",
        last_sync_report=None,
        last_error="fetch failed",
    )
    assert failed["last_error"] == "fetch failed"
