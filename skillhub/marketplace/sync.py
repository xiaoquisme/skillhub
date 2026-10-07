"""Sync and import engine (U3, KTD3, KTD4, KTD5, KD4).

Applies a parsed upstream skill set to SkillHub's storage and database through
the existing publish path (locks + atomic staging). Change detection is
content-based on three states of the same skill: the content hash recorded at
import, the stored files, and the incoming upstream files — which is what
makes upstream updates and local-edit detection (KD4) both work.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Optional

from skillhub.database import Database
from skillhub.marketplace.models import ParseResult, UpstreamSkill
from skillhub.storage import SkillStorage


@dataclass
class SyncReport:
    """Outcome of one sync run, persisted on the source as JSON."""

    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    skipped_conflicts: list[str] = field(default_factory=list)
    skipped_local_edits: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "added": self.added,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "missing": self.missing,
            "skipped_conflicts": self.skipped_conflicts,
            "skipped_local_edits": self.skipped_local_edits,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def content_digest(files: dict[str, bytes]) -> str:
    """Stable digest over a skill's file map (path + content hash)."""
    hasher = hashlib.sha256()
    for path in sorted(files):
        hasher.update(path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(files[path]).hexdigest().encode("ascii"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def _content_type(filename: str) -> str:
    return "text/markdown" if filename.endswith(".md") else "application/octet-stream"


def _stored_files(storage: SkillStorage, skill_id: str, project_id: Optional[str]) -> dict[str, bytes]:
    try:
        return storage.read_bundle_files(skill_id, project_id)
    except FileNotFoundError:
        return {}


async def sync_source(
    db: Database,
    storage: SkillStorage,
    source: dict,
    result: Optional[ParseResult],
    revision: str,
    error: Optional[str] = None,
) -> SyncReport:
    """Sync one marketplace source. ``result=None`` means fetch/parse failed.

    Fetch/parse failure (``error``) records the error and performs no skill
    writes at all (R10).
    """
    report = SyncReport()

    if error is not None or result is None:
        report.errors.append(error or "fetch or parse failed")
        await db.touch_marketplace_sync(
            source["id"],
            last_revision=source.get("last_revision"),
            last_sync_report=json.dumps(report.to_dict()),
            last_error=error or "fetch or parse failed",
        )
        return report

    report.warnings.extend(result.warnings)
    seen_paths: set[str] = set()

    for upstream in result.skills:
        seen_paths.add(upstream.path)
        await _apply_skill(db, storage, source, upstream, revision, report)

    await _flag_missing(db, storage, source, seen_paths, report)

    await db.touch_marketplace_sync(
        source["id"],
        last_revision=revision,
        last_sync_report=json.dumps(report.to_dict()),
        last_error=None,
    )
    return report


async def _apply_skill(
    db: Database,
    storage: SkillStorage,
    source: dict,
    upstream: UpstreamSkill,
    revision: str,
    report: SyncReport,
) -> None:
    name = upstream.name
    project_id = source.get("project_id")
    incoming_digest = content_digest(upstream.files)

    existing = await db.get_skill_by_upstream(source["id"], upstream.path)

    if existing is not None:
        skill_id = existing["id"]
        stored = _stored_files(storage, skill_id, project_id)
        stored_digest = content_digest(stored) if stored else None
        if stored_digest is not None and stored_digest != (existing.get("imported_hash") or stored_digest):
            # Stored content diverged from the recorded import: locally edited (KD4).
            report.skipped_local_edits.append(name)
            return
        if existing.get("imported_hash") == incoming_digest and stored_digest == incoming_digest:
            report.unchanged.append(name)
            return
        async with storage.lock("skill:" + skill_id):
            await _write_skill(db, storage, skill_id, source, upstream, revision, incoming_digest)
        report.updated.append(name)
        return

    # Name-lookup hit without matching provenance is a conflict (KTD5).
    by_name = await db.get_skill_by_name(name, project_id)
    if by_name is not None:
        report.skipped_conflicts.append(name)
        return

    skill_id = None
    async with storage.lock("name:" + json.dumps([project_id, name])):
        by_name = await db.get_skill_by_name(name, project_id)
        if by_name is not None:
            report.skipped_conflicts.append(name)
            return
        skill_id = str(uuid.uuid4())
        async with storage.lock("skill:" + skill_id):
            await db.create_skill(
                name=name,
                display_name=None,
                description=upstream.description or None,
                category=upstream.plugin or None,
                tags=[],
                author=None,
                license=None,
                published_by=None,
                project_id=project_id,
                skill_id=skill_id,
                marketplace_source_id=source["id"],
                upstream_path=upstream.path,
                upstream_version=upstream.version,
                upstream_revision=revision,
                upstream_status="active",
                imported_hash=incoming_digest,
            )
            _write_files(storage, skill_id, upstream.files, project_id)
            for filename, content in upstream.files.items():
                await db.add_skill_file(
                    skill_id, filename, _content_type(filename), len(content)
                )
    report.added.append(name)


async def _write_skill(
    db: Database,
    storage: SkillStorage,
    skill_id: str,
    source: dict,
    upstream: UpstreamSkill,
    revision: str,
    incoming_digest: str,
) -> None:
    _write_files(storage, skill_id, upstream.files, source.get("project_id"))
    await db.delete_skill_files(skill_id)
    for filename, content in upstream.files.items():
        await db.add_skill_file(
            skill_id, filename, _content_type(filename), len(content)
        )
    await db.update_skill(
        skill_id,
        description=upstream.description or None,
        upstream_version=upstream.version,
        upstream_revision=revision,
        upstream_status="active",
        imported_hash=incoming_digest,
    )


def _write_files(
    storage: SkillStorage,
    skill_id: str,
    files: dict[str, bytes],
    project_id: Optional[str],
) -> None:
    with storage.publication_files(
        skill_id,
        [(path, content, _content_type(path)) for path, content in files.items()],
        project_id,
    ):
        pass


async def _flag_missing(
    db: Database,
    storage: SkillStorage,
    source: dict,
    seen_paths: set[str],
    report: SyncReport,
) -> None:
    for skill in await db.list_skills_for_source(source["id"]):
        if skill["upstream_path"] in seen_paths:
            continue
        await db.update_skill(skill["id"], upstream_status="missing-upstream")
        report.missing.append(skill["name"])
