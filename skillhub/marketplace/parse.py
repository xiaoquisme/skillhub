"""Catalog parsing for marketplace sources (U2, KTD2, KTD7).

Normalizes Claude Code catalogs (``.claude-plugin/marketplace.json``), Codex
catalogs (``.agents/plugins/marketplace.json``), and bare skills trees into
``UpstreamSkill`` records. Everything risky about upstream content is handled
here: plugin-source resolution is confined to the checkout (or an explicit
second fetch), filenames are validated, and symlinks/non-regular files are
skipped with a warning.
"""

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional

from skillhub.marketplace.models import ParseError, ParseResult, UpstreamSkill
from skillhub.parsing import parse_frontmatter
from skillhub.storage import SkillStorage

_CATALOG_PATHS = (
    Path(".agents") / "plugins" / "marketplace.json",
    Path(".claude-plugin") / "marketplace.json",
)
_BARE_SKILL_DIRS = (Path("skills"), Path(".agents") / "skills")

# Plugin source forms KTD7 skips with a structured warning.
_UNSUPPORTED_SOURCES = {"npm", "archive", "command"}
_EXTERNAL_SOURCES = {"github", "url", "git-subdir"}


def parse_checkout(
    root: Path,
    revision: str,
    fetch: Optional[Callable] = None,
) -> ParseResult:
    """Parse a checkout into skill records and reportable warnings.

    ``fetch(location, ref)`` is an optional context-manager factory yielding a
    checkout directory, used for git-backed plugin sources that live outside
    the marketplace checkout.
    """
    root = root.resolve()
    result = ParseResult()

    catalog_path = next((p for p in _CATALOG_PATHS if (root / p).is_file()), None)
    if catalog_path is not None:
        catalog = _load_json(root / catalog_path)
        result.skills.extend(
            _parse_catalog(root, catalog, revision, fetch, result.warnings)
        )
    else:
        result.skills.extend(_parse_bare_tree(root, revision, result.warnings))
        if not result.skills:
            raise ParseError(
                "No marketplace manifest (.agents/plugins/marketplace.json or "
                ".claude-plugin/marketplace.json) and no skills tree found"
            )

    if not result.skills and not result.warnings:
        raise ParseError("Marketplace catalog contains no importable skills")
    return result


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ParseError(f"Invalid manifest {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError(f"Invalid manifest {path.name}: not an object")
    return data


def _parse_catalog(
    root: Path,
    catalog: dict,
    revision: str,
    fetch: Optional[Callable],
    warnings: list[str],
) -> list[UpstreamSkill]:
    skills: list[UpstreamSkill] = []
    entries = catalog.get("plugins")
    if not isinstance(entries, list):
        raise ParseError("Marketplace manifest has no plugins array")

    for entry in entries:
        if not isinstance(entry, dict):
            warnings.append(f"Skipped malformed plugin entry: {entry!r}")
            continue
        name = entry.get("name") or "unnamed"
        source = entry.get("source")
        try:
            with _plugin_checkout(root, source, fetch) as (base, plugin_root):
                if plugin_root is None:
                    kind = _source_kind(source)
                    warnings.append(
                        f"Skipped plugin {name}: unsupported source type {kind!r}"
                    )
                    continue
                version = _resolve_version(plugin_root, entry.get("version"), revision)
                skills.extend(
                    _collect_plugin_skills(base, plugin_root, name, version, warnings)
                )
        except ParseError as exc:
            warnings.append(f"Skipped plugin {name}: {exc}")
    return skills


def _source_kind(source) -> str:
    if isinstance(source, dict):
        return str(source.get("source", "unknown"))
    return "relative"


@contextmanager
def _plugin_checkout(
    root: Path, source, fetch: Optional[Callable]
) -> Iterator[tuple[Path, Optional[Path]]]:
    """Yield (path_base, plugin_root); plugin_root None marks an unsupported form.

    ``path_base`` is the directory upstream paths are recorded relative to.
    """
    if isinstance(source, str):
        yield root, _resolve_relative(root, source)
        return

    if not isinstance(source, dict):
        raise ParseError(f"Unrecognized plugin source {source!r}")

    kind = source.get("source")
    if kind in _UNSUPPORTED_SOURCES:
        yield root, None
        return
    if kind == "local":
        yield root, _resolve_relative(root, source.get("path", ""))
        return
    if kind in _EXTERNAL_SOURCES:
        location = source.get("url") or source.get("repo")
        if not location:
            raise ParseError(f"External source has no url/repo: {source!r}")
        if fetch is None:
            raise ParseError(f"External source {location!r} needs a fetcher")
        ref = source.get("ref") or source.get("sha")
        with fetch(location, ref) as checkout_root:
            plugin_root = checkout_root
            if kind == "git-subdir":
                sub = source.get("path", "")
                plugin_root = checkout_root / sub
                if not plugin_root.is_dir():
                    raise ParseError(f"Fetched source has no {sub!r} directory")
            yield checkout_root, plugin_root
        return
    raise ParseError(f"Unrecognized plugin source {source!r}")


def _resolve_relative(root: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel.startswith("./"):
        raise ParseError(f"Plugin path must start with './': {rel!r}")
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise ParseError(f"Plugin path escapes the marketplace root: {rel!r}")
    if not candidate.is_dir():
        raise ParseError(f"Plugin directory not found: {rel!r}")
    return candidate


def _resolve_version(plugin_root: Path, entry_version, revision: str) -> str:
    manifest_version = None
    for manifest in (
        plugin_root / ".claude-plugin" / "plugin.json",
        plugin_root / "plugin.json",
    ):
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text())
                manifest_version = data.get("version")
            except (OSError, json.JSONDecodeError):
                pass
            break
    return manifest_version or entry_version or revision


def _collect_plugin_skills(
    base: Path,
    plugin_root: Path,
    plugin_name: str,
    version: str,
    warnings: list[str],
) -> list[UpstreamSkill]:
    skills: list[UpstreamSkill] = []
    skills_dir = plugin_root / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                skills.append(
                    _build_skill(base, child, plugin_name, version, warnings)
                )
    elif (plugin_root / "SKILL.md").is_file():
        skills.append(
            _build_skill(base, plugin_root, plugin_name, version, warnings)
        )
    return skills


def _parse_bare_tree(root: Path, revision: str, warnings: list[str]) -> list[UpstreamSkill]:
    skills: list[UpstreamSkill] = []
    for base in _BARE_SKILL_DIRS:
        base_dir = root / base
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                skills.append(_build_skill(root, child, "", revision, warnings))
    return skills


def _build_skill(
    base: Path,
    skill_dir: Path,
    plugin_name: str,
    version: str,
    warnings: list[str],
) -> UpstreamSkill:
    files: dict[str, bytes] = {}
    for path in sorted(skill_dir.rglob("*")):
        rel = path.relative_to(skill_dir).as_posix()
        if path.is_symlink() or not path.is_file():
            warnings.append(
                f"Skipped non-regular upstream file {rel!r} in {skill_dir.name}"
            )
            continue
        try:
            SkillStorage.validate_filename(rel)
        except ValueError:
            warnings.append(
                f"Skipped unsafe upstream filename {rel!r} in {skill_dir.name}"
            )
            continue
        files[rel] = path.read_bytes()

    frontmatter = parse_frontmatter(
        files.get("SKILL.md", b"").decode("utf-8", "replace")
    )
    name = frontmatter.get("name") or skill_dir.name
    return UpstreamSkill(
        name=name,
        description=str(frontmatter.get("description") or ""),
        path=skill_dir.relative_to(base).as_posix(),
        plugin=plugin_name,
        version=version,
        files=files,
    )
