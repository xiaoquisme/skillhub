"""File storage operations for SkillHub."""

import asyncio
import fcntl
import hashlib
import os
import shutil
import tempfile
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Optional


class SkillStorage:
    """Manages skill file storage on the local filesystem."""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lock(self, key: str):
        """Coordinate complete operations across workers without blocking the event loop.

        Locks live outside skill directories so deletion cannot unlink a held lock.
        """
        lock_dir = self.skills_dir.parent / ("." + self.skills_dir.name + "-locks")
        lock_dir.mkdir(parents=True, exist_ok=True)
        if lock_dir.is_symlink():
            raise ValueError("Unsafe lock directory")
        path = lock_dir / hashlib.sha256(key.encode()).hexdigest()
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.01)
            yield
        finally:
            os.close(fd)

    @staticmethod
    def validate_filename(filename: str) -> None:
        if not filename or "\\" in filename or any(ord(c) < 32 for c in filename):
            raise ValueError("Unsafe skill file path")
        if filename.startswith("/") or any(part in ("", ".", "..") for part in filename.split("/")):
            raise ValueError("Unsafe skill file path")
        if ":" in filename.split("/")[0]:
            raise ValueError("Unsafe skill file path")

    def _safe_path(self, skill_id: str, filename: str, project_id: Optional[str] = None) -> Path:
        self.validate_filename(filename)
        base = self._skill_path(skill_id, project_id)
        path = base / filename
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError("Symlinks are not allowed in skill files")
            if parent == self.skills_dir:
                break
        return path

    def read_bundle_files(self, skill_id: str, project_id: Optional[str] = None) -> dict[str, bytes]:
        """Read complete bytes; caller holds the operation lock with metadata reads."""
        base = self._skill_path(skill_id, project_id)
        self._safe_path(skill_id, "SKILL.md", project_id)
        if not base.is_dir():
            raise FileNotFoundError("Skill files not found")
        files = {}
        for path in sorted(base.rglob("*")):
            filename = path.relative_to(base).as_posix()
            safe = self._safe_path(skill_id, filename, project_id)
            if safe.is_file():
                files[filename] = safe.read_bytes()
            elif not safe.is_dir():
                raise ValueError("Unsupported skill file")
        if "SKILL.md" not in files:
            raise FileNotFoundError("SKILL.md not found")
        return files

    @contextmanager
    def publication_files(self, skill_id: str, uploads: list[tuple], project_id: Optional[str] = None):
        """Stage a complete directory, restoring the previous one on publication failure.

        Caller holds the skill lock until both files and database changes finish.
        """
        self._safe_path(skill_id, "SKILL.md", project_id)
        destination = self._skill_path(skill_id, project_id)
        with tempfile.TemporaryDirectory(prefix=".skillhub-publish-", dir=self.skills_dir) as temporary:
            staged = Path(temporary) / "new"
            previous = Path(temporary) / "previous"
            had_files = destination.exists()
            if had_files:
                shutil.copytree(destination, staged, symlinks=True)
            else:
                staged.mkdir()
            for filename, content, _ in uploads:
                path = staged / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if had_files:
                destination.rename(previous)
            try:
                staged.rename(destination)
                yield
            except BaseException:
                if destination.exists():
                    shutil.rmtree(destination)
                if had_files:
                    previous.rename(destination)
                raise

    def _skill_path(self, skill_id: str, project_id: Optional[str] = None) -> Path:
        """Get the path for a skill's files, namespaced by project."""
        for component in (skill_id, project_id or "default"):
            self.validate_filename(component)
            if "/" in component:
                raise ValueError("Unsafe skill identifier")
        if project_id:
            return self.skills_dir / project_id / skill_id
        return self.skills_dir / "default" / skill_id

    def save_skill_files(self, skill_id: str, files: dict[str, bytes], project_id: Optional[str] = None) -> None:
        """Save skill files to disk.

        Args:
            skill_id: The skill's unique ID.
            files: Dict of filename -> content bytes.
            project_id: Optional project ID for namespacing.
        """
        skill_dir = self._skill_path(skill_id, project_id)
        skill_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in files.items():
            file_path = self._safe_path(skill_id, filename, project_id)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

    def save_skill_file(self, skill_id: str, filename: str, content: bytes, project_id: Optional[str] = None) -> None:
        """Save a single skill file to disk."""
        file_path = self._safe_path(skill_id, filename, project_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

    def get_skill_file(self, skill_id: str, filename: str, project_id: Optional[str] = None) -> Optional[bytes]:
        """Retrieve a skill file's content."""
        file_path = self._safe_path(skill_id, filename, project_id)
        if file_path.exists():
            return file_path.read_bytes()
        return None

    def get_skill_file_path(self, skill_id: str, filename: str, project_id: Optional[str] = None) -> Optional[Path]:
        """Get the path to a skill file."""
        file_path = self._safe_path(skill_id, filename, project_id)
        if file_path.exists():
            return file_path
        return None

    def list_skill_files(self, skill_id: str, project_id: Optional[str] = None) -> list[str]:
        """List all files in a skill directory."""
        skill_dir = self._skill_path(skill_id, project_id)
        if not skill_dir.exists():
            return []

        files = []
        for path in skill_dir.rglob("*"):
            if path.is_file():
                rel = path.relative_to(skill_dir)
                files.append(str(rel))
        return sorted(files)

    def delete_skill(self, skill_id: str, project_id: Optional[str] = None) -> bool:
        """Delete all files for a skill."""
        skill_dir = self._skill_path(skill_id, project_id)
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            return True
        return False

    def skill_exists(self, skill_id: str, project_id: Optional[str] = None) -> bool:
        """Check if a skill directory exists."""
        return self._skill_path(skill_id, project_id).is_dir()

    def get_skill_size(self, skill_id: str, project_id: Optional[str] = None) -> int:
        """Get total size of a skill's files in bytes."""
        skill_dir = self._skill_path(skill_id, project_id)
        if not skill_dir.exists():
            return 0
        return sum(f.stat().st_size for f in skill_dir.rglob("*") if f.is_file())

    def migrate_legacy_skills(self) -> int:
        """Move legacy skill directories from root to default/ subdirectory.

        Returns the number of skills migrated.
        """
        default_dir = self.skills_dir / "default"
        migrated = 0

        for item in self.skills_dir.iterdir():
            if item.is_dir() and item.name != "default":
                # Check if this looks like a legacy skill dir (has SKILL.md or skill files)
                target = default_dir / item.name
                if not target.exists():
                    default_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item), str(target))
                    migrated += 1

        return migrated
