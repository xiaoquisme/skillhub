"""Search skills in the registry."""
import click
import httpx
from skillhub.config import load_config
@click.command()
@click.argument("query")
@click.option("--category", "-c", help="Filter by category")
@click.option("--limit", "-n", default=20, help="Max results")
@click.option("--server", help="Override registry server URL")
@click.option("--project", "-p", default=None, help="Project name (uses default_project from config if omitted)")
def search(query: str, category: str, limit: int, server: str, project: str):
    """Search for skills in the registry."""
    config = load_config()
    registry_url = server or config.registry_url

    # Resolve project: CLI flag > config default
    project_name = project or config.default_project

    params = {"q": query, "limit": limit}
    if category:
        params["category"] = category
    if project_name:
        params["project"] = project_name

    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{registry_url}/api/skills", params=params)

        if response.status_code != 200:
            click.echo(f"Error: Failed to search ({response.status_code})", err=True)
            raise SystemExit(1)

        skills = response.json()

        if not skills:
            click.echo(f"No skills found for '{query}'")
            return

        click.echo(f"Found {len(skills)} skill(s):\n")

        for skill in skills:
            name = skill["name"]
            desc = skill.get("description", "No description")[:60]
            cat = skill.get("category", "")
            tags = skill.get("tags", [])
            downloads = skill.get("download_count", 0)
            proj = skill.get("project", "")

            click.echo(f"  {name}")
            click.echo(f"    {desc}")
            if proj:
                click.echo(f"    Project: {proj}")
            if cat:
                click.echo(f"    Category: {cat}")
            if tags:
                click.echo(f"    Tags: {', '.join(tags)}")
            if downloads:
                click.echo(f"    Downloads: {downloads}")
            click.echo()
