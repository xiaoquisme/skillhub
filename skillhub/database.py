"""SQLite database operations for SkillHub."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skills (
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

CREATE TABLE IF NOT EXISTS skill_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT DEFAULT 'text/markdown',
    size_bytes INTEGER,
    UNIQUE(skill_id, filename)
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK(role IN ('admin', 'publisher', 'viewer')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketplace_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    location TEXT NOT NULL,
    source_ref TEXT,
    project_id TEXT DEFAULT NULL,
    sync_interval_minutes INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    last_revision TEXT,
    last_error TEXT,
    last_sync_report TEXT,
    last_synced_at TIMESTAMP
);
"""

ALLOWED_SORT_FIELDS = {"created_at", "updated_at", "name", "category", "download_count"}


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.commit()

        # Migration: add download_count column to existing databases
        try:
            await self._conn.execute(
                "ALTER TABLE skills ADD COLUMN download_count INTEGER DEFAULT 0"
            )
            await self._conn.commit()
        except aiosqlite.OperationalError:
            pass  # Column already exists

        # Migration: add project_id column to existing databases
        try:
            await self._conn.execute(
                "ALTER TABLE skills ADD COLUMN project_id TEXT DEFAULT NULL"
            )
            await self._conn.commit()
        except aiosqlite.OperationalError:
            pass  # Column already exists

        # Migration: add marketplace provenance columns to existing databases
        for column in (
            "marketplace_source_id TEXT DEFAULT NULL",
            "upstream_path TEXT",
            "upstream_version TEXT",
            "upstream_revision TEXT",
            "upstream_status TEXT",
            "imported_hash TEXT",
        ):
            try:
                await self._conn.execute(f"ALTER TABLE skills ADD COLUMN {column}")
                await self._conn.commit()
            except aiosqlite.OperationalError:
                pass  # Column already exists

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    def _build_filter(
        self, query: Optional[str], category: Optional[str], project_id: Optional[str] = None
    ) -> tuple[list[str], list]:
        conditions, params = [], []
        if query:
            conditions.append(
                "(name LIKE ? OR display_name LIKE ? OR description LIKE ?)"
            )
            q = f"%{query}%"
            params.extend([q, q, q])
        if category:
            conditions.append("category = ?")
            params.append(category)
        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)
        return conditions, params

    # --- Projects CRUD ---

    async def create_project(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        project_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        await self.conn.execute(
            """INSERT INTO projects (id, name, display_name, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, name, display_name, description, now, now),
        )
        await self.conn.commit()
        return await self.get_project(project_id)

    async def get_project(self, project_id: str) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_project_by_name(self, name: str) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def update_project(self, project_id: str, **kwargs) -> Optional[dict]:
        kwargs["updated_at"] = datetime.now(UTC).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [project_id]

        await self.conn.execute(
            f"UPDATE projects SET {set_clause} WHERE id = ?", values
        )
        await self.conn.commit()
        return await self.get_project(project_id)

    async def delete_project(self, project_id: str) -> bool:
        async with self.conn.execute(
            "DELETE FROM projects WHERE id = ?", (project_id,)
        ) as cursor:
            await self.conn.commit()
            return cursor.rowcount > 0

    async def list_projects(self) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def count_skills_in_project(self, project_id: str) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM skills WHERE project_id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    # --- Skills CRUD ---

    async def create_skill(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        author: Optional[str] = None,
        license: Optional[str] = None,
        published_by: Optional[str] = None,
        project_id: Optional[str] = None,
        skill_id: Optional[str] = None,
        marketplace_source_id: Optional[str] = None,
        upstream_path: Optional[str] = None,
        upstream_version: Optional[str] = None,
        upstream_revision: Optional[str] = None,
        upstream_status: Optional[str] = None,
        imported_hash: Optional[str] = None,
    ) -> dict:
        skill_id = skill_id or str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        tags_json = json.dumps(tags or [])

        await self.conn.execute(
            """INSERT INTO skills (id, name, display_name, description, category,
               tags, author, license, created_at, updated_at, published_by, project_id,
               marketplace_source_id, upstream_path, upstream_version,
               upstream_revision, upstream_status, imported_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (skill_id, name, display_name, description, category,
             tags_json, author, license, now, now, published_by, project_id,
             marketplace_source_id, upstream_path, upstream_version,
             upstream_revision, upstream_status, imported_hash),
        )
        await self.conn.commit()
        return await self.get_skill(skill_id)

    async def restore_publication(self, skill_id: str, previous: Optional[dict], files: list[dict]) -> None:
        """Restore only publication-owned DB state after an ordinary write failure."""
        if previous is None:
            await self.delete_skill(skill_id)
            return
        fields = ("display_name", "description", "category", "tags", "author", "license", "updated_at")
        await self.conn.execute(
            "UPDATE skills SET " + ", ".join(field + " = ?" for field in fields) + " WHERE id = ?",
            [previous.get(field) for field in fields] + [skill_id],
        )
        await self.conn.execute("DELETE FROM skill_files WHERE skill_id = ?", (skill_id,))
        await self.conn.executemany(
            "INSERT INTO skill_files (id, skill_id, filename, content_type, size_bytes) VALUES (?, ?, ?, ?, ?)",
            [(file["id"], skill_id, file["filename"], file.get("content_type"), file.get("size_bytes")) for file in files],
        )
        await self.conn.commit()

    async def get_skill(self, skill_id: str) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM skills WHERE id = ?", (skill_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_skill_by_name(self, name: str, project_id: Optional[str] = None) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM skills WHERE name = ? AND project_id IS ?",
            (name, project_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def update_skill(self, skill_id: str, **kwargs) -> Optional[dict]:
        kwargs["updated_at"] = datetime.now(UTC).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [skill_id]

        await self.conn.execute(
            f"UPDATE skills SET {set_clause} WHERE id = ?", values
        )
        await self.conn.commit()
        return await self.get_skill(skill_id)

    async def delete_skill(self, skill_id: str) -> bool:
        async with self.conn.execute(
            "DELETE FROM skills WHERE id = ?", (skill_id,)
        ) as cursor:
            await self.conn.commit()
            return cursor.rowcount > 0

    async def list_skills(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        project_id: Optional[str] = None,
        sort: str = "updated_at",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions, params = self._build_filter(query, category, project_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sort_col = sort if sort in ALLOWED_SORT_FIELDS else "updated_at"
        order = f" ORDER BY {sort_col} DESC"
        params.extend([limit, offset])

        async with self.conn.execute(
            f"SELECT * FROM skills{where}{order} LIMIT ? OFFSET ?", params
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def count_skills(
        self, query: Optional[str] = None, category: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> int:
        conditions, params = self._build_filter(query, category, project_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""

        async with self.conn.execute(
            f"SELECT COUNT(*) FROM skills{where}", params
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    # --- Skill Files ---

    async def add_skill_file(
        self,
        skill_id: str,
        filename: str,
        content_type: str = "text/markdown",
        size_bytes: Optional[int] = None,
    ) -> None:
        await self.conn.execute(
            """INSERT OR REPLACE INTO skill_files (skill_id, filename, content_type, size_bytes)
               VALUES (?, ?, ?, ?)""",
            (skill_id, filename, content_type, size_bytes),
        )
        await self.conn.commit()

    async def get_skill_files(self, skill_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM skill_files WHERE skill_id = ? ORDER BY filename",
            (skill_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def delete_skill_files(self, skill_id: str) -> None:
        await self.conn.execute(
            "DELETE FROM skill_files WHERE skill_id = ?", (skill_id,)
        )
        await self.conn.commit()

    async def increment_download_count(self, skill_id: str) -> None:
        """Atomically increment the download count for a skill."""
        await self.conn.execute(
            "UPDATE skills SET download_count = download_count + 1 WHERE id = ?",
            (skill_id,),
        )
        await self.conn.commit()

    async def get_skill_by_upstream(
        self, marketplace_source_id: str, upstream_path: str
    ) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM skills WHERE marketplace_source_id = ? AND upstream_path = ?",
            (marketplace_source_id, upstream_path),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def list_skills_for_source(self, marketplace_source_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM skills WHERE marketplace_source_id = ? ORDER BY name",
            (marketplace_source_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def count_skills_for_source(self, marketplace_source_id: str) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM skills WHERE marketplace_source_id = ?",
            (marketplace_source_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def count_skills_by_source(self) -> dict[str, int]:
        async with self.conn.execute(
            "SELECT marketplace_source_id, COUNT(*) AS n FROM skills "
            "WHERE marketplace_source_id IS NOT NULL GROUP BY marketplace_source_id"
        ) as cursor:
            rows = await cursor.fetchall()
            return {row["marketplace_source_id"]: row["n"] for row in rows}

    # --- Marketplace Sources CRUD ---

    async def create_marketplace_source(
        self,
        name: str,
        location: str,
        source_ref: Optional[str] = None,
        project_id: Optional[str] = None,
        sync_interval_minutes: int = 0,
        enabled: int = 1,
    ) -> dict:
        source_id = str(uuid.uuid4())
        await self.conn.execute(
            """INSERT INTO marketplace_sources
               (id, name, location, source_ref, project_id, sync_interval_minutes, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source_id, name, location, source_ref, project_id,
             sync_interval_minutes, enabled),
        )
        await self.conn.commit()
        return await self.get_marketplace_source(source_id)

    async def get_marketplace_source(self, source_id: str) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM marketplace_sources WHERE id = ?", (source_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_marketplace_source_by_name(self, name: str) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM marketplace_sources WHERE name = ?", (name,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_marketplace_sources(self) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM marketplace_sources ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_marketplace_source(self, source_id: str, **kwargs) -> Optional[dict]:
        if not kwargs:
            return await self.get_marketplace_source(source_id)
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [source_id]
        await self.conn.execute(
            f"UPDATE marketplace_sources SET {set_clause} WHERE id = ?", values
        )
        await self.conn.commit()
        return await self.get_marketplace_source(source_id)

    async def delete_marketplace_source(self, source_id: str) -> bool:
        async with self.conn.execute(
            "DELETE FROM marketplace_sources WHERE id = ?", (source_id,)
        ) as cursor:
            await self.conn.commit()
            return cursor.rowcount > 0

    async def delete_skills_by_source(self, marketplace_source_id: str) -> int:
        """Remove skill and skill_file rows for a source; disk files are the caller's job."""
        async with self.conn.execute(
            "SELECT id FROM skills WHERE marketplace_source_id = ?",
            (marketplace_source_id,),
        ) as cursor:
            skill_ids = [row["id"] for row in await cursor.fetchall()]
        for skill_id in skill_ids:
            await self.conn.execute(
                "DELETE FROM skill_files WHERE skill_id = ?", (skill_id,)
            )
        async with self.conn.execute(
            "DELETE FROM skills WHERE marketplace_source_id = ?",
            (marketplace_source_id,),
        ) as cursor:
            deleted = cursor.rowcount
        await self.conn.commit()
        return deleted

    async def touch_marketplace_sync(
        self,
        source_id: str,
        last_revision: Optional[str] = None,
        last_sync_report: Optional[str] = None,
        last_error: Optional[str] = None,
    ) -> Optional[dict]:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """UPDATE marketplace_sources
               SET last_revision = ?, last_sync_report = ?, last_error = ?, last_synced_at = ?
               WHERE id = ?""",
            (last_revision, last_sync_report, last_error, now, source_id),
        )
        await self.conn.commit()
        return await self.get_marketplace_source(source_id)

    # --- Users CRUD ---

    async def create_user(
        self,
        username: str,
        password_hash: str,
        role: str = "viewer",
    ) -> dict:
        user_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        await self.conn.execute(
            """INSERT INTO users (id, username, password_hash, role, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username, password_hash, role, now, now),
        )
        await self.conn.commit()
        return await self.get_user(user_id)

    async def get_user(self, user_id: str) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_user_by_username(self, username: str) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def update_user(self, user_id: str, **kwargs) -> Optional[dict]:
        kwargs["updated_at"] = datetime.now(UTC).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [user_id]

        await self.conn.execute(
            f"UPDATE users SET {set_clause} WHERE id = ?", values
        )
        await self.conn.commit()
        return await self.get_user(user_id)

    async def delete_user(self, user_id: str) -> bool:
        async with self.conn.execute(
            "DELETE FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            await self.conn.commit()
            return cursor.rowcount > 0

    async def list_users(self) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
