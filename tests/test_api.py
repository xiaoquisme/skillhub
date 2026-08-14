"""Tests for API endpoints."""

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
from skillhub.storage import SkillStorage


@pytest.fixture
def admin_token():
    """Create a JWT token for an admin user."""
    return create_token("admin-user-id", "admin")


@pytest.fixture
def publisher_token():
    """Create a JWT token for a publisher user."""
    return create_token("publisher-user-id", "publisher")


@pytest.fixture
def viewer_token():
    """Create a JWT token for a viewer user."""
    return create_token("viewer-user-id", "viewer")


def auth_headers(token: str) -> dict:
    """Create Authorization headers with a Bearer token."""
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_skills_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        # Create admin user for auth
        admin_user = await test_db.create_user(
            username="test-admin",
            password_hash=hash_password("pass"),
            role="admin",
        )
        token = create_token(admin_user["id"], "admin")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/skills", headers=auth_headers(token))
            assert response.status_code == 200
            assert response.json() == []

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_database_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        await db.connect()

        skill = await db.create_skill(
            name="test-skill",
            display_name="Test Skill",
            description="A test skill",
            category="testing",
            tags=["python", "test"],
        )
        assert skill["name"] == "test-skill"

        fetched = await db.get_skill(skill["id"])
        assert fetched is not None
        assert fetched["name"] == "test-skill"

        updated = await db.update_skill(skill["id"], description="Updated")
        assert updated["description"] == "Updated"

        deleted = await db.delete_skill(skill["id"])
        assert deleted is True
        assert await db.get_skill(skill["id"]) is None

        await db.close()


@pytest.mark.asyncio
async def test_storage_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = SkillStorage(Path(tmpdir))

        storage.save_skill_file("skill-1", "SKILL.md", b"# Hello")
        content = storage.get_skill_file("skill-1", "SKILL.md")
        assert content == b"# Hello"

        files = storage.list_skill_files("skill-1")
        assert len(files) == 1

        storage.delete_skill("skill-1")
        assert not storage.skill_exists("skill-1")


@pytest.mark.asyncio
async def test_skill_response_includes_download_count():
    """Test that skill API responses include download_count."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        # Create admin user for auth
        admin_user = await test_db.create_user(
            username="test-admin",
            password_hash=hash_password("pass"),
            role="admin",
        )
        token = create_token(admin_user["id"], "admin")

        # Create a skill via the database directly
        skill = await test_db.create_skill(
            name="downloadable-skill",
            description="A skill for testing downloads",
            category="testing",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # List skills and check download_count is present
            response = await client.get("/api/skills", headers=auth_headers(token))
            assert response.status_code == 200
            skills = response.json()
            assert len(skills) == 1
            assert skills[0]["download_count"] == 0

            # Get skill detail and check download_count
            response = await client.get(f"/api/skills/{skill['id']}", headers=auth_headers(token))
            assert response.status_code == 200
            detail = response.json()
            assert detail["download_count"] == 0

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_delete_skill():
    """Test DELETE /api/skills/{id} returns 204 and removes the skill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        storage = SkillStorage(test_config.storage.skills_dir)
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db
        deps._storage = storage

        # Create an admin user for auth
        admin_user = await test_db.create_user(
            username="admin-delete-test",
            password_hash=hash_password("pass123"),
            role="admin",
        )
        token = create_token(admin_user["id"], "admin")

        # Create a skill
        skill = await test_db.create_skill(
            name="deletable-skill",
            display_name="Deletable Skill",
            description="A skill to be deleted",
            category="testing",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Delete the skill with auth
            response = await client.delete(
                f"/api/skills/{skill['id']}",
                headers=auth_headers(token),
            )
            assert response.status_code == 204

            # Verify it's gone via GET
            response = await client.get(f"/api/skills/{skill['id']}", headers=auth_headers(token))
            assert response.status_code == 404

            # Verify it's absent from the list
            response = await client.get("/api/skills", headers=auth_headers(token))
            assert response.status_code == 200
            skills = response.json()
            assert all(s["id"] != skill["id"] for s in skills)

        await test_db.close()
        deps._db = None
        deps._config = None
        deps._storage = None


@pytest.mark.asyncio
async def test_delete_skill_not_found():
    """Test DELETE /api/skills/{nonexistent} returns 404."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        # Create an admin user for auth
        admin_user = await test_db.create_user(
            username="admin-notfound-test",
            password_hash=hash_password("pass123"),
            role="admin",
        )
        token = create_token(admin_user["id"], "admin")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                "/api/skills/nonexistent-id",
                headers=auth_headers(token),
            )
            assert response.status_code == 404

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_download_increments_count():
    """Test that downloading a file increments the skill's download_count."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        storage = SkillStorage(test_config.storage.skills_dir)
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db
        deps._storage = storage

        # Create admin user for auth
        admin_user = await test_db.create_user(
            username="test-admin",
            password_hash=hash_password("pass"),
            role="admin",
        )
        token = create_token(admin_user["id"], "admin")

        # Create a skill with a file
        skill = await test_db.create_skill(name="dl-skill")
        storage.save_skill_file(skill["id"], "SKILL.md", b"# Download me")
        await test_db.add_skill_file(skill["id"], "SKILL.md", "text/markdown", 15)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Verify initial count
            response = await client.get("/api/skills", headers=auth_headers(token))
            assert response.json()[0]["download_count"] == 0

            # Download the file
            response = await client.get(
                f"/api/skills/{skill['id']}/files/SKILL.md",
                headers=auth_headers(token),
            )
            assert response.status_code == 200

            # Verify count incremented
            response = await client.get("/api/skills", headers=auth_headers(token))
            assert response.json()[0]["download_count"] == 1

            # Download again
            response = await client.get(
                f"/api/skills/{skill['id']}/files/SKILL.md",
                headers=auth_headers(token),
            )
            assert response.status_code == 200

            # Verify count is now 2
            response = await client.get("/api/skills", headers=auth_headers(token))
            assert response.json()[0]["download_count"] == 2

        await test_db.close()
        deps._db = None
        deps._config = None
        deps._storage = None


# ============================================================
# U8: Auth-related tests
# ============================================================

@pytest.mark.asyncio
async def test_login_success():
    """Test successful login returns a JWT token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        # Create a user
        await test_db.create_user(
            username="testuser",
            password_hash=hash_password("testpass"),
            role="publisher",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "testpass"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_login_failure_wrong_password():
    """Test login with wrong password returns 401."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        await test_db.create_user(
            username="testuser2",
            password_hash=hash_password("correctpass"),
            role="viewer",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "testuser2", "password": "wrongpass"},
            )
            assert response.status_code == 401

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_login_failure_nonexistent_user():
    """Test login with nonexistent user returns 401."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "nobody", "password": "nopass"},
            )
            assert response.status_code == 401

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_auth_required_for_publish():
    """Test that publishing a skill requires authentication."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        storage = SkillStorage(test_config.storage.skills_dir)
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db
        deps._storage = storage

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Try to publish without auth
            response = await client.post(
                "/api/skills",
                data={"name": "unauth-skill"},
            )
            assert response.status_code == 401

        await test_db.close()
        deps._db = None
        deps._config = None
        deps._storage = None


@pytest.mark.asyncio
async def test_auth_required_for_delete():
    """Test that deleting a skill requires authentication."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        skill = await test_db.create_skill(name="protected-skill")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Try to delete without auth
            response = await client.delete(f"/api/skills/{skill['id']}")
            assert response.status_code == 401

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_read_endpoints_require_auth():
    """Test that read endpoints require authentication."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        skill = await test_db.create_skill(name="protected-skill")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # List skills without auth - should be rejected
            response = await client.get("/api/skills")
            assert response.status_code == 401

            # Get skill detail without auth - should be rejected
            response = await client.get(f"/api/skills/{skill['id']}")
            assert response.status_code == 401

            # With auth - should work
            admin_user = await test_db.create_user(
                username="test-admin",
                password_hash=hash_password("pass"),
                role="admin",
            )
            token = create_token(admin_user["id"], "admin")
            response = await client.get("/api/skills", headers=auth_headers(token))
            assert response.status_code == 200

            response = await client.get(f"/api/skills/{skill['id']}", headers=auth_headers(token))
            assert response.status_code == 200

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_publisher_cannot_delete_others_skill():
    """Test that a publisher cannot delete another user's skill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        storage = SkillStorage(test_config.storage.skills_dir)
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db
        deps._storage = storage

        # Create two publisher users
        user_alice = await test_db.create_user(
            username="alice",
            password_hash=hash_password("pass123"),
            role="publisher",
        )
        user_bob = await test_db.create_user(
            username="bob",
            password_hash=hash_password("pass456"),
            role="publisher",
        )

        # Bob creates a skill
        skill = await test_db.create_skill(
            name="bobs-skill",
            published_by=user_bob["id"],
        )

        # Alice tries to delete Bob's skill
        alice_token = create_token(user_alice["id"], "publisher")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/skills/{skill['id']}",
                headers=auth_headers(alice_token),
            )
            assert response.status_code == 403

        await test_db.close()
        deps._db = None
        deps._config = None
        deps._storage = None


@pytest.mark.asyncio
async def test_publisher_can_delete_own_skill():
    """Test that a publisher can delete their own skill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        storage = SkillStorage(test_config.storage.skills_dir)
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db
        deps._storage = storage

        user = await test_db.create_user(
            username="own-publisher",
            password_hash=hash_password("pass123"),
            role="publisher",
        )

        skill = await test_db.create_skill(
            name="own-skill",
            published_by=user["id"],
        )

        token = create_token(user["id"], "publisher")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/skills/{skill['id']}",
                headers=auth_headers(token),
            )
            assert response.status_code == 204

        await test_db.close()
        deps._db = None
        deps._config = None
        deps._storage = None


@pytest.mark.asyncio
async def test_admin_can_delete_any_skill():
    """Test that admin can delete any skill regardless of ownership."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        storage = SkillStorage(test_config.storage.skills_dir)
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db
        deps._storage = storage

        # Create a publisher and admin
        publisher = await test_db.create_user(
            username="publisher-for-admin-test",
            password_hash=hash_password("pass123"),
            role="publisher",
        )
        admin = await test_db.create_user(
            username="admin-for-delete-test",
            password_hash=hash_password("pass456"),
            role="admin",
        )

        # Publisher creates a skill
        skill = await test_db.create_skill(
            name="publisher-skill-admin-delete",
            published_by=publisher["id"],
        )

        admin_token = create_token(admin["id"], "admin")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/skills/{skill['id']}",
                headers=auth_headers(admin_token),
            )
            assert response.status_code == 204

        await test_db.close()
        deps._db = None
        deps._config = None
        deps._storage = None


@pytest.mark.asyncio
async def test_publish_sets_published_by():
    """Test that publishing a skill sets the published_by field."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        storage = SkillStorage(test_config.storage.skills_dir)
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db
        deps._storage = storage

        user = await test_db.create_user(
            username="publisher-set-test",
            password_hash=hash_password("pass123"),
            role="publisher",
        )

        token = create_token(user["id"], "publisher")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/skills",
                data={"name": "published-skill"},
                headers=auth_headers(token),
            )
            assert response.status_code == 201
            data = response.json()
            assert data["published_by"] == user["id"]

        await test_db.close()
        deps._db = None
        deps._config = None
        deps._storage = None


@pytest.mark.asyncio
async def test_user_list_requires_admin():
    """Test that listing users requires admin role."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        # Create a non-admin user
        viewer = await test_db.create_user(
            username="viewer-for-admin-test",
            password_hash=hash_password("pass123"),
            role="viewer",
        )

        viewer_token = create_token(viewer["id"], "viewer")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Viewer cannot list users
            response = await client.get(
                "/api/users",
                headers=auth_headers(viewer_token),
            )
            assert response.status_code == 403

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_admin_can_list_users():
    """Test that admin can list all users."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        admin = await test_db.create_user(
            username="admin-list-test",
            password_hash=hash_password("pass123"),
            role="admin",
        )

        await test_db.create_user(
            username="user-list-test",
            password_hash=hash_password("pass456"),
            role="viewer",
        )

        admin_token = create_token(admin["id"], "admin")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/users",
                headers=auth_headers(admin_token),
            )
            assert response.status_code == 200
            users = response.json()
            assert len(users) >= 2

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_admin_create_user():
    """Test that admin can create a new user."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        admin = await test_db.create_user(
            username="admin-create-test",
            password_hash=hash_password("pass123"),
            role="admin",
        )

        admin_token = create_token(admin["id"], "admin")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/users",
                json={
                    "username": "newuser",
                    "password": "newpass",
                    "role": "publisher",
                },
                headers=auth_headers(admin_token),
            )
            assert response.status_code == 201
            data = response.json()
            assert data["username"] == "newuser"
            assert data["role"] == "publisher"

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_admin_delete_user():
    """Test that admin can delete a user (but not themselves)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        admin = await test_db.create_user(
            username="admin-delete-user-test",
            password_hash=hash_password("pass123"),
            role="admin",
        )
        target = await test_db.create_user(
            username="target-user",
            password_hash=hash_password("pass456"),
            role="viewer",
        )

        admin_token = create_token(admin["id"], "admin")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Delete target user
            response = await client.delete(
                f"/api/users/{target['id']}",
                headers=auth_headers(admin_token),
            )
            assert response.status_code == 204

            # Try to delete self
            response = await client.delete(
                f"/api/users/{admin['id']}",
                headers=auth_headers(admin_token),
            )
            assert response.status_code == 400

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_change_password():
    """Test that a user can change their own password."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        user = await test_db.create_user(
            username="pw-change-test",
            password_hash=hash_password("oldpass"),
            role="publisher",
        )

        token = create_token(user["id"], "publisher")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Change password
            response = await client.post(
                "/api/auth/change-password",
                json={"old_password": "oldpass", "new_password": "newpass"},
                headers=auth_headers(token),
            )
            assert response.status_code == 200

            # Try logging in with old password - should fail
            response = await client.post(
                "/api/auth/login",
                json={"username": "pw-change-test", "password": "oldpass"},
            )
            assert response.status_code == 401

            # Try logging in with new password - should succeed
            response = await client.post(
                "/api/auth/login",
                json={"username": "pw-change-test", "password": "newpass"},
            )
            assert response.status_code == 200

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_invalid_token_rejected():
    """Test that an invalid JWT token is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Try to publish with invalid token
            response = await client.post(
                "/api/skills",
                data={"name": "invalid-token-skill"},
                headers={"Authorization": "Bearer invalid.token.here"},
            )
            assert response.status_code == 401

        await test_db.close()
        deps._db = None
        deps._config = None


# ============================================================
# Multi-Project Tests
# ============================================================

@pytest.mark.asyncio
async def test_create_project():
    """Test creating a project via API."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        admin_user = await test_db.create_user(
            username="admin-project-test",
            password_hash=hash_password("pass"),
            role="admin",
        )
        token = create_token(admin_user["id"], "admin")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/projects",
                json={"name": "alpha", "display_name": "Alpha Project"},
                headers=auth_headers(token),
            )
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "alpha"
            assert data["display_name"] == "Alpha Project"
            assert "id" in data

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_same_skill_name_different_projects():
    """Test that the same skill name can exist in different projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        storage = SkillStorage(test_config.storage.skills_dir)
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db
        deps._storage = storage

        admin_user = await test_db.create_user(
            username="admin-multi-proj",
            password_hash=hash_password("pass"),
            role="admin",
        )
        token = create_token(admin_user["id"], "admin")

        # Create two projects
        proj_alpha = await test_db.create_project(name="alpha")
        proj_beta = await test_db.create_project(name="beta")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Publish same skill name to both projects
            response = await client.post(
                "/api/skills",
                data={"name": "debugging", "project": "alpha"},
                headers=auth_headers(token),
            )
            assert response.status_code == 201

            response = await client.post(
                "/api/skills",
                data={"name": "debugging", "project": "beta"},
                headers=auth_headers(token),
            )
            assert response.status_code == 201

            # List all skills - should see both
            response = await client.get("/api/skills", headers=auth_headers(token))
            assert response.status_code == 200
            skills = response.json()
            assert len(skills) == 2

            # Filter by project alpha
            response = await client.get(
                "/api/skills?project=alpha", headers=auth_headers(token)
            )
            assert response.status_code == 200
            skills = response.json()
            assert len(skills) == 1
            assert skills[0]["name"] == "debugging"

        await test_db.close()
        deps._db = None
        deps._config = None
        deps._storage = None


@pytest.mark.asyncio
async def test_project_delete_blocks_with_skills():
    """Test that deleting a project with skills is blocked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        admin_user = await test_db.create_user(
            username="admin-delete-proj",
            password_hash=hash_password("pass"),
            role="admin",
        )
        token = create_token(admin_user["id"], "admin")

        # Create project with a skill
        proj = await test_db.create_project(name="doomed")
        await test_db.create_skill(name="orphan", project_id=proj["id"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/projects/{proj['id']}", headers=auth_headers(token)
            )
            assert response.status_code == 409

        await test_db.close()
        deps._db = None
        deps._config = None


@pytest.mark.asyncio
async def test_non_admin_cannot_create_project():
    """Test that non-admin users cannot create projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_config = AppConfig(
            storage=StorageConfig(
                data_dir=tmpdir_path / "data",
                skills_dir=tmpdir_path / "skills",
            ),
        )
        test_db = Database(test_config.storage.data_dir / "skillhub.db")
        await test_db.connect()

        deps._config = test_config
        deps._db = test_db

        publisher = await test_db.create_user(
            username="pub-no-proj",
            password_hash=hash_password("pass"),
            role="publisher",
        )
        token = create_token(publisher["id"], "publisher")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/projects",
                json={"name": "nope"},
                headers=auth_headers(token),
            )
            assert response.status_code == 403

        await test_db.close()
        deps._db = None
        deps._config = None
