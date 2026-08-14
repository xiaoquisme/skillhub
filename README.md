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

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
