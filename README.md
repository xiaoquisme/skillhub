# SkillHub

A lightweight, self-hosted skill registry for Hermes Agent skills. Supports multi-project mode — each project owns an isolated skill namespace.

## Quick Start (Server)

Deploy SkillHub with Docker:

```bash
git clone https://github.com/xiaoquisme/skill-hub.git
cd skillhub
./quickstart.sh
```

Open http://localhost/ui/ in your browser.

### Or run locally

```bash
pip install -e .
uvicorn skillhub.main:app --reload
```

## Client CLI

Install the CLI to push and install skills from a SkillHub server:

```bash
uv tool install git+https://github.com/xiaoquisme/skill-hub.git
```

### Configure the server

Create `~/.skillhub/config.yaml`:

```yaml
registry_url: http://<server-host>:80
default_project: my-project  # optional: default project for CLI commands
```

### Usage

```bash
# Publish a skill (to default_project from config)
skillhub push ./my-skill/

# Publish to a specific project
skillhub push ./my-skill/ -p alpha

# Install a skill
skillhub install skill-name

# Install from a specific project
skillhub install skill-name -p alpha

# Search skills
skillhub search keyword

# Search within a project
skillhub search keyword -p alpha

# List available skills
skillhub list

# List skills in a project
skillhub list -p alpha
```

## Multi-Project Mode

SkillHub supports multiple projects, each with its own isolated skill namespace. The same skill name can exist in different projects without conflict.

### API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/projects` | any | List all projects |
| POST | `/api/projects` | admin | Create a project |
| GET | `/api/projects/{id}` | any | Get project details |
| PUT | `/api/projects/{id}` | admin | Update a project |
| DELETE | `/api/projects/{id}` | admin | Delete a project (must have no skills) |

All skill endpoints accept an optional `?project=<name>` query parameter to filter by project.

### CLI Flags

All CLI commands (`push`, `install`, `search`, `list`) accept `--project` / `-p` to specify a project. When omitted, uses `default_project` from config.

### Web UI

The web interface shows a project selector dropdown in the navbar. Select a project to filter the skill list. Your selection persists across page reloads.

## Configuration

Server configuration is stored in `~/.skillhub/config.yaml`:

```yaml
server:
  host: 127.0.0.1
  port: 8000
storage:
  data_dir: ~/.skillhub/data
  skills_dir: ~/.skillhub/skills
default_project: my-project  # optional: default project for CLI commands
```

Environment variables override YAML values:

| Variable | Overrides |
|----------|-----------|
| `SKILLHUB_HOST` | `server.host` |
| `SKILLHUB_PORT` | `server.port` |
| `SKILLHUB_DATA_DIR` | `storage.data_dir` |
| `SKILLHUB_SKILLS_DIR` | `storage.skills_dir` |
| `SKILLHUB_DEFAULT_PROJECT` | `default_project` |

## Workbench Current Bundle

Authenticated consumers can fetch `GET /api/workbench/skills/{skill_id}/bundle`
using the existing `Authorization: Bearer <JWT>` credential. Keep that credential
on the consuming server. This endpoint does not change JWT roles or permissions.

The response contains `id`, `name`, `description`, `files`, and `contentDigest`.
Files include `SKILL.md` and every stored dependency (scripts, references, binary
assets), sorted by relative path. Each entry contains `path`, `encoding: "base64"`,
`content`, byte `size`, and hexadecimal SHA-256 `sha256`. `contentDigest` is the
SHA-256 of the UTF-8 concatenation of each sorted `path + "\0" + sha256 + "\0"`.
Missing skills or missing `SKILL.md` return 404; unsafe paths and symlinks return
400. Upload paths are validated before publication changes metadata or files.

Bundle reads, complete publications, and deletions share OS file locks across
workers on the same filesystem. Lock files are stored in a sibling directory
`.<skills-directory-name>-locks`, which must be writable and shared by those
workers. Complete publication directories are staged before replacement. Ordinary file
or database write failures restore previous files and publication metadata, or
remove a failed new publication, while retaining the lock. Reads cannot observe
a publication or deletion in progress. Process termination and failure of the
rollback itself are outside this guarantee; no crash recovery or distributed
database support is provided.
Publication keeps the existing file upsert behavior; files omitted from an
update remain stored. There is no user-selectable version or version pinning.

## Marketplace Sources

Admins can register external skill marketplaces as import sources. SkillHub
fetches the repository, reads its catalog, and imports every skill it finds as
a normal SkillHub skill — searchable, downloadable, and installable through the
existing API and CLI.

Supported catalog formats:

- Claude Code plugin marketplaces (`.claude-plugin/marketplace.json`)
- Codex plugin marketplaces (`.agents/plugins/marketplace.json`)
- Bare skills trees (`skills/*/SKILL.md`, `.agents/skills/*/SKILL.md`) when no
  catalog manifest exists

Source locations must be git repositories: `https`/`ssh`/`file` URLs or
`owner/repo` GitHub shorthand. Plain directory paths are rejected. Plugin
entries using `npm`, `archive`, or `command` sources are skipped with a warning;
relative, `github`, `url`, and `git-subdir` sources are supported.

Manage sources from the admin page or the API:

- `GET /api/marketplaces` / `POST` / `PATCH` / `DELETE /api/marketplaces/{id}`
  (mutations are admin-only; a unique name is required at creation)
- `POST /api/marketplaces/{id}/sync` runs a manual sync and returns the report
- `GET /api/marketplaces/{id}/skills` lists imported skills with upstream status
- `sync_interval_minutes > 0` enables periodic in-process sync (off by default)

Sync semantics:

- Change detection is content-based per skill; re-syncs only touch skills whose
  upstream content changed.
- Imported skills keep their identity and download count across updates.
- Skills removed upstream are flagged `missing-upstream` and kept until an
  admin deletes them. Sync never deletes.
- Name collisions with skills not imported by the same source are skipped and
  reported — locally published skills are never overwritten.
- Locally edited imported skills win: the next sync skips and reports them
  instead of overwriting the edit.
- Removing a source deletes the skills it imported (the admin UI shows the
  count first).
- A failed fetch or parse leaves previously imported state untouched and
  records the error on the source.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
