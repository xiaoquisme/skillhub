"""Push (publish) a skill to the registry."""
import json
from pathlib import Path
import click
import httpx

from skillhub.config import load_config
from skillhub.parsing import parse_frontmatter

def parse_skill_md(path: Path) -> dict:
    """Parse SKILL.md from a skill directory, falling back to dir name."""
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        click.echo(f"Error: No SKILL.md found in {path}", err=True)
        raise SystemExit(1)

    content = skill_md.read_text()
    result = parse_frontmatter(content)
    return result if result else {"name": path.name}

def collect_files(path: Path) -> list[tuple[str, bytes]]:
    files = []
    for file_path in path.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            rel = file_path.relative_to(path)
            files.append((str(rel), file_path.read_bytes()))
    return files

@click.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--force", is_flag=True, help="Overwrite existing skill")
@click.option("--server", help="Override registry server URL")
@click.option("--project", "-p", default=None, help="Project name (uses default_project from config if omitted)")
def push(path: Path, force: bool, server: str, project: str):
    """Publish a skill to the registry.

    PATH is the directory containing SKILL.md and skill files.
    """
    config = load_config()
    registry_url = server or config.registry_url

    # Resolve project: CLI flag > config default
    project_name = project or config.default_project

    metadata = parse_skill_md(path)
    name = metadata.get("name", path.name)

    click.echo(f"Publishing skill: {name}")
    if project_name:
        click.echo(f"  Project: {project_name}")

    files = collect_files(path)
    click.echo(f"  Files: {len(files)}")

    headers = {}
    if config.api_token:
        headers["Authorization"] = f"Bearer {config.api_token}"

    with httpx.Client(timeout=30.0) as client:
        data = {
            "name": name,
            "display_name": metadata.get("display_name", ""),
            "description": metadata.get("description", ""),
            "category": metadata.get("category", ""),
            "tags": json.dumps(metadata.get("tags", [])),
            "author": metadata.get("author", ""),
            "license": metadata.get("license", ""),
        }
        if project_name:
            data["project"] = project_name

        upload_files = []
        for filename, content in files:
            upload_files.append(("files", (filename, content, "application/octet-stream")))

        response = client.post(
            f"{registry_url}/api/skills",
            data=data,
            files=upload_files,
            headers=headers,
        )

        if response.status_code == 201:
            skill = response.json()
            click.echo(f"  Published: {skill['name']} (id: {skill['id'][:8]}...)")
        else:
            click.echo(f"Error: {response.status_code} - {response.text}", err=True)
            raise SystemExit(1)
