---
title: Multi-Project Mode - Plan
type: feat
date: 2026-08-14
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

# Multi-Project Mode - Plan

## Goal Capsule

Add multi-project support to SkillHub so each project owns an isolated skill namespace, with a configurable default project for CLI convenience. A single SkillHub instance can serve multiple teams/contexts without skill name collisions across projects.

**Authority hierarchy:** Project isolation is the primary invariant — skill name uniqueness must be scoped to a project, never global. The default project is a UX convenience, not an architectural commitment.

**Stop conditions:** All API endpoints accept and filter by project; CLI commands support `--project`; config supports `default_project`; existing single-project usage works unchanged (backward compatible).

## Product Contract

### Summary

SkillHub currently stores all skills in a flat namespace. This plan adds a `projects` concept: each project is a named namespace that scopes skill names, and the admin can set a default project so CLI commands don't need `--project` every time.

### Problem Frame

Users managing skills for multiple teams or contexts (e.g., personal vs work, different products) hit name collisions. A "debugging" skill for project A conflicts with a "debugging" skill for project B. Multi-project mode gives each context its own namespace.

### Requirements

- **R1.** Projects table: a `projects` table with `id`, `name` (unique), `display_name`, `description`, `created_at`, `updated_at`.
- **R2.** Skills belong to a project: add `project_id` FK to the `skills` table. Skills without a project_id belong to a "default" implicit project for backward compatibility.
- **R3.** Skill name uniqueness scoped to project: `UNIQUE(name, project_id)` instead of `UNIQUE(name)`.
- **R4.** API project parameter: all skill CRUD endpoints accept an optional `?project=<name>` query parameter. When omitted, skills from all projects are returned (or filtered by default_project if configured).
- **R5.** API project CRUD: endpoints to create, list, update, and delete projects.
- **R6.** CLI `--project` flag: `push`, `install`, `search`, `list` commands accept `--project` / `-p`.
- **R7.** Config `default_project`: `AppConfig` gains `default_project: Optional[str]` field. CLI commands use this when `--project` is not provided.
- **R8.** Web UI project selector: a dropdown in the navbar to filter skills by project, with an "All Projects" option.
- **R9.** Storage: skill file directories are namespaced under `skills_dir/<project_id>/<skill_id>/` (or `skills_dir/default/<skill_id>/` for legacy skills).
- **R10.** Migration: existing databases get an `ALTER TABLE skills ADD COLUMN project_id TEXT` with NULL default. Existing skills stay in the default (no project) namespace.

### Scope Boundaries

- Out of scope: cross-project skill sharing/forking, project-level permissions, project archival.
- The default project is a naming convenience — it does not change storage paths or database schema for skills that already exist.

### Acceptance Examples

1. Admin creates project "alpha" via API. Publisher pushes skill "debugging" to "alpha". Publisher pushes skill "debugging" to "beta" — no conflict.
2. CLI `skillhub push ./my-skill/` uses the default project from config.
3. CLI `skillhub list -p alpha` shows only skills in the "alpha" project.
4. Existing skills without a project_id continue to work without migration friction.

## Planning Contract

### Key Technical Decisions

**KTD1. Project as namespace (not as folder).** Projects are a database concept (FK on skills), not a filesystem-only concept. This keeps the API clean and avoids path-traversal edge cases. File storage is organized under `skills_dir/<project_id>/<skill_id>/` for new skills.

**KTD2. Backward compatibility via NULL project_id.** Existing skills have `project_id = NULL`, treated as belonging to an implicit "default" namespace. This avoids a breaking migration and lets old CLI versions work.

**KTD3. Skill name uniqueness is (name, project_id).** SQLite enforces `UNIQUE(name, project_id)` — same name can exist in different projects but not in the same project. NULL project_id values are not considered duplicates by SQLite's UNIQUE constraint (NULL != NULL).

**KTD4. Default project in config, not in DB.** The default project is a CLI/client-side convenience stored in `~/.skillhub/config.yaml`. The server does not assume a default — it returns all projects' skills unless explicitly filtered.

### Assumptions

- The project count will be small (tens, not thousands), so no pagination on the projects list endpoint is needed initially.
- The implicit default namespace (NULL project_id) is a transition aid, not a long-term state.

### Implementation Constraints

- SQLite does not enforce UNIQUE with NULL columns in the expected way for partial uniqueness. We handle project_id NULL as "default namespace" at the application layer.
- The `--project` flag in CLI is a client-side default resolution; the API never assumes a default.

### Sequencing

1. Database schema + models (R1, R2, R3) — foundation
2. Storage path update (R9) — file layer
3. API endpoints (R4, R5) — server layer
4. CLI commands (R6, R7) — client layer
5. Config changes (R7) — shared config
6. Web UI (R8) — frontend
7. Tests — verification

## Implementation Units

### U1. Database Schema & Models

**Goal:** Add projects table and project_id FK to skills, update Pydantic models.

**Requirements:** R1, R2, R3

**Files:**
- `skillhub/models.py` — add ProjectBase, ProjectCreate, ProjectResponse models
- `skillhub/database.py` — add projects table DDL, project CRUD methods, update skills queries to filter by project_id

**Approach:**
1. Add `CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, display_name TEXT, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)` to SCHEMA.
2. Add `ALTER TABLE skills ADD COLUMN project_id TEXT DEFAULT NULL` migration in `connect()`.
3. Add project CRUD methods: `create_project`, `get_project`, `get_project_by_name`, `update_project`, `delete_project`, `list_projects`.
4. Update `list_skills` to accept `project_id` parameter for filtering.
5. Update `create_skill` to accept `project_id`.
6. Update `_build_filter` to handle project filtering.

**Test Scenarios:**
- Create/list/update/delete projects
- Create skills in different projects with same name
- Filter skills by project
- Backward compatibility: existing skills without project_id still work

### U2. Storage Path Update

**Goal:** Namespace skill file storage under project directories.

**Requirements:** R9

**Files:**
- `skillhub/storage.py` — update `_skill_path` to include project_id in path

**Approach:**
1. Change `_skill_path` signature to include `project_id: Optional[str] = None`.
2. Path becomes `skills_dir / (project_id or "default") / skill_id`.
3. Update all callers in `api/skills.py` and tests.
4. Add migration helper to move legacy skill dirs into `default/` subdirectory.

**Test Scenarios:**
- Save/load/delete skill files with project_id
- Legacy skills in root skills_dir still accessible

### U3. API Project Endpoints

**Goal:** CRUD endpoints for projects, and project filtering on skill endpoints.

**Requirements:** R4, R5

**Files:**
- `skillhub/api/projects.py` — new router for project CRUD
- `skillhub/api/skills.py` — add project query parameter to list/detail/publish/delete
- `skillhub/main.py` — include projects router

**Approach:**
1. Create `skillhub/api/projects.py` with router prefix `/api/projects`.
2. Endpoints: GET /api/projects, POST /api/projects, GET /api/projects/{id}, PUT /api/projects/{id}, DELETE /api/projects/{id}.
3. Add `project` query param to GET /api/skills, POST /api/skills, GET /api/skills/{id}, DELETE /api/skills/{id}.
4. For POST /api/skills, project can be specified as form field or query param.
5. Include project info in SkillResponse (project_id field).

**Test Scenarios:**
- Create project, publish skill to it, list skills filtered by project
- Same skill name in different projects
- Delete project cascades to skills (or blocks if skills exist)

### U4. CLI Commands

**Goal:** Add --project flag to push, install, search, list commands.

**Requirements:** R6, R7

**Files:**
- `skillhub/cli/commands/push.py` — add --project/-p option
- `skillhub/cli/commands/install.py` — add --project/-p option
- `skillhub/cli/commands/search.py` — add --project/-p option
- `skillhub/cli/commands/list_cmd.py` — add --project/-p option

**Approach:**
1. Add `@click.option("--project", "-p", default=None, help="Project name")` to each command.
2. When --project is not provided, use `config.default_project`.
3. Pass project as query parameter or form field in API calls.
4. Display project name in search/list output.

**Test Scenarios:**
- Push skill to specific project
- List skills filtered by project
- Default project from config used when --project omitted

### U5. Config Changes

**Goal:** Add default_project to AppConfig.

**Requirements:** R7

**Files:**
- `skillhub/config.py` — add `default_project: Optional[str] = None` to AppConfig

**Approach:**
1. Add field to AppConfig model.
2. CLI commands read `config.default_project` when --project not provided.
3. Document in README and AGENTS.md.

**Test Scenarios:**
- Config with default_project set, CLI uses it
- Config without default_project, CLI works (no default)

### U6. Web UI Project Selector

**Goal:** Add project dropdown to navbar for filtering.

**Requirements:** R8

**Files:**
- `skillhub/static/index.html` — add project selector dropdown
- `skillhub/static/js/app.js` — handle project filter
- `skillhub/static/js/api.js` — add project API calls

**Approach:**
1. Add a `<select id="project-filter">` in the navbar next to category filter.
2. Fetch projects from /api/projects on page load.
3. Add "All Projects" option as default.
4. When project selected, filter skill list by project.
5. Store selected project in localStorage for persistence.

**Test Scenarios:**
- Project dropdown loads and filters skills
- Selection persists across page reloads

### U7. Tests

**Goal:** Comprehensive tests for multi-project functionality.

**Files:**
- `tests/test_api.py` — add project CRUD tests and project-scoped skill tests
- `tests/test_database.py` — add project database tests
- `tests/test_storage.py` — add project-scoped storage tests

**Approach:**
1. Test project CRUD via API.
2. Test skill CRUD scoped to projects.
3. Test backward compatibility (skills without project_id).
4. Test same skill name in different projects.
5. Test default project resolution in CLI.

## Verification Contract

- Run `pytest` from the worktree root — all existing + new tests must pass.
- Manual test: create project, push skill, verify isolation, verify default project works.

## Definition of Done

- [ ] Projects table exists in schema with CRUD methods
- [ ] Skills table has project_id column, queries filter by project
- [ ] API endpoints support project filtering
- [ ] CLI commands support --project flag
- [ ] Config supports default_project
- [ ] Web UI has project selector
- [ ] All existing tests pass
- [ ] New tests cover multi-project scenarios
- [ ] Backward compatibility verified (NULL project_id)
