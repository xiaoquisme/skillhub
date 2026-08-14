"""Install a skill from the registry."""
import json
from pathlib import Path
import click
import httpx

from skillhub.config import load_config

@click.command()
@click.argument("name")
@click.option("--category", "-c", help="Install to specific category subdirectory")
@click.option("--server", help="Override registry server URL")
@click.option("--project", "-p", default=None, help="Project name (uses default_project from config if omitted)")
def install(name: str, category: str, server: str, project: str):
    """Install a skill from the registry to ~/.hermes/skills/."""
    config = load_config()
    registry_url = server or config.registry_url

    # Resolve project: CLI flag > config default
    project_name = project or config.default_project

    click.echo(f"Installing skill: {name}")
    if project_name:
        click.echo(f"  Project: {project_name}")

    with httpx.Client(timeout=30.0) as client:
        # Search for the skill by name
        params = {"q": name}
        if project_name:
            params["project"] = project_name

        response = client.get(
            f"{registry_url}/api/skills",
            params=params,
        )

        if response.status_code != 200:
            click.echo(f"Error: Failed to search skills ({response.status_code})", err=True)
            raise SystemExit(1)

        skills = response.json()
        if not skills:
            click.echo(f"Error: Skill '{name}' not found", err=True)
            raise SystemExit(1)

        # Find exact match
        skill = None
        for s in skills:
            if s["name"] == name:
                skill = s
                break

        if not skill:
            # Use first result as closest match
            skill = skills[0]
            click.echo(f"  Using closest match: {skill['name']}")

        skill_id = skill["id"]
        skill_name = skill["name"]
        skill_category = skill.get("category") or category or "uncategorized"

        # Get skill details
        response = client.get(f"{registry_url}/api/skills/{skill_id}")
        if response.status_code != 200:
            click.echo(f"Error: Failed to get skill details", err=True)
            raise SystemExit(1)

        detail = response.json()

        # Determine install path
        hermes_skills = Path.home() / ".hermes" / "skills"
        install_dir = hermes_skills / skill_category / skill_name

        if install_dir.exists():
            click.echo(f"  Skill already exists at {install_dir}")
            if not click.confirm("Overwrite?"):
                click.echo("Aborted.")
                return

        install_dir.mkdir(parents=True, exist_ok=True)

        # Download all files
        files = detail.get("files", [])
        click.echo(f"  Files: {len(files)}")

        for file_info in files:
            filename = file_info["filename"]
            response = client.get(
                f"{registry_url}/api/skills/{skill_id}/files/{filename}"
            )

            if response.status_code == 200:
                file_path = install_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(response.content)
                click.echo(f"    {filename}")
            else:
                click.echo(f"    Warning: Failed to download {filename}", err=True)

    click.echo(f"\nInstalled {skill_name} to {install_dir}")
    click.echo(f"  Use it in Hermes: skill_view(name='{skill_name}')")
