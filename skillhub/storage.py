"""File storage operations for SkillHub."""

import shutil
from pathlib import Path
from typing import Optional


class SkillStorage:
    """Manages skill file storage on the local filesystem."""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def _skill_path(self, skill_id: str, project_id: Optional[str] = None) -> Path:
        """Get the path for a skill's files, namespaced by project."""
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
            file_path = skill_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

    def save_skill_file(self, skill_id: str, filename: str, content: bytes, project_id: Optional[str] = None) -> None:
        """Save a single skill file to disk."""
        skill_dir = self._skill_path(skill_id, project_id)
        file_path = skill_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

    def get_skill_file(self, skill_id: str, filename: str, project_id: Optional[str] = None) -> Optional[bytes]:
        """Retrieve a skill file's content."""
        file_path = self._skill_path(skill_id, project_id) / filename
        if file_path.exists():
            return file_path.read_bytes()
        return None

    def get_skill_file_path(self, skill_id: str, filename: str, project_id: Optional[str] = None) -> Optional[Path]:
        """Get the path to a skill file."""
        file_path = self._skill_path(skill_id, project_id) / filename
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
