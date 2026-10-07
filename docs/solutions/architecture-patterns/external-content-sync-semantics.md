---
title: "Sync semantics for importing external content: provenance-keyed identity and three-state change detection"
date: 2026-10-06
category: architecture-patterns
module: skillhub-marketplace
problem_type: architecture_pattern
component: data-sync-engine
severity: high
applies_when:
  - "Building or extending a sync that imports content from an external source into local records users can also edit"
  - "Deciding how to detect what changed on re-sync, or how to key imported records"
  - "Any mirror-style import where local edits and upstream updates can both change the same record"
tags:
  - sync
  - marketplace
  - provenance
  - change-detection
  - local-edit-detection
  - import
---

# Sync semantics for importing external content: provenance-keyed identity and three-state change detection

## Context

The marketplace sync imports skills from external git marketplaces into SkillHub's
existing storage, where admins can later edit them through the ordinary publish
path. Two naive designs were each rejected during plan review because they lose
data in ways that tests are unlikely to catch until someone complains:

1. **Change detection by revision equality** ("repo SHA moved → re-import
   everything") marks every imported skill `updated` on every sync, even when
   only an unrelated file changed upstream.
2. **Change detection by comparing upstream content to stored content**
   ("differs → update") cannot distinguish "upstream changed" from "a human
   edited the local copy" — so the next sync silently overwrites local edits.

## Guidance

**Key imported records by provenance, never by name.** The stable identity of an
imported skill is `(marketplace_source_id, upstream_path)` (implemented in
`Database.get_skill_by_upstream`, `skillhub/database.py`). Names collide and
upstream can rename things; the source + path pair is what "this import" means.
A name-lookup hit with different provenance is a *conflict* — skip and report —
not an update target.

**Record the imported content hash at import time and compare three states on
sync.** Store `imported_hash` (the digest of the file set as it was imported)
on the record. Change detection then compares three values, not two:

| stored == imported_hash? | upstream == imported_hash? | Meaning | Action |
|---|---|---|---|
| yes | yes | nothing changed | leave alone (`unchanged`) |
| yes | no | upstream changed | update (`updated`) |
| no | — | locally edited | **skip and report** (`skipped_local_edits`) |

See `content_digest` / `_apply_skill` in `skillhub/marketplace/sync.py`. The
`imported_hash` column is what makes the third row distinguishable — with only
stored-vs-upstream comparison it is invisible.

**Sync never deletes; explicit actions delete.** Upstream removals set a status
flag (`missing-upstream`) and keep the record. Only an explicit admin action
(deleting the source or the skill) removes data.

## Why This Matters

The failure modes are silent: a sync that overwrites local edits or churns
`updated` on every run *runs green* — tests asserting "sync imports and updates"
pass either way. The data loss surfaces later, when an admin's edit disappears
or the report lies about what changed. A third-state hash costs one column and
makes both failure modes testable (assert `skipped_local_edits`, assert
`unchanged` is populated on a no-op re-sync).

## When to Apply

- Importing/syncing content from external sources (marketplaces, registries,
  upstream repos) into records that users can also modify locally.
- Deciding the key for imported rows: prefer stable upstream coordinates
  (source id + upstream path) over display names.
- Writing sync reports: separate `updated` (upstream moved) from
  `skipped_local_edits` (local divergence) and `unchanged` — do not collapse
  them.

## Examples

From `tests/test_marketplace_sync.py`:

```python
# Re-sync with changed upstream content: same id, download count preserved
report = await sync_source(db, storage, source, second_parse, "rev2")
assert report.updated == ["alpha"]
after = await db.get_skill_by_upstream(source["id"], "p/a")
assert after["id"] == before["id"]

# Re-sync with NO upstream change: the unchanged bucket must be reachable
report = await sync_source(db, storage, source, same_parse, "rev2")
assert report.unchanged == ["alpha"]

# Locally edited skill: skip and report, never overwrite
report = await sync_source(db, storage, source, changed_parse, "rev2")
assert report.skipped_local_edits == ["alpha"]
assert b"local edit" in storage.read_bundle_files(skill["id"], None)["SKILL.md"]
```

## Related

- Plan and KTDs: `docs/plans/2026-10-06-0050-feat-claude-codex-marketplace-sources-plan.md`
  (KD3 "sync never deletes", KD4 "local edits win", KTD4 provenance columns,
  KTD5 conflict policy)
- Name-upsert semantics that motivated the conflict rule:
  `docs/conventions/gotchas.md` ("Skill name is upsert")
