"""Project CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request

from skillhub.api.deps import get_db, require_auth
from skillhub.database import Database
from skillhub.models import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_from_row(row: dict) -> ProjectResponse:
    return ProjectResponse(
        id=row["id"],
        name=row["name"],
        display_name=row.get("display_name"),
        description=row.get("description"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    request: Request,
    db: Database = Depends(get_db),
):
    await require_auth(request, db)
    projects = await db.list_projects()
    return [_project_from_row(p) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    request: Request,
    project: ProjectCreate,
    db: Database = Depends(get_db),
):
    current_user = await require_auth(request, db)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create projects")

    existing = await db.get_project_by_name(project.name)
    if existing:
        raise HTTPException(status_code=409, detail="Project with this name already exists")

    record = await db.create_project(
        name=project.name,
        display_name=project.display_name,
        description=project.description,
    )
    return _project_from_row(record)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    request: Request,
    db: Database = Depends(get_db),
):
    await require_auth(request, db)
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_from_row(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    request: Request,
    project: ProjectCreate,
    db: Database = Depends(get_db),
):
    current_user = await require_auth(request, db)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update projects")

    existing = await db.get_project(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check name uniqueness if changing name
    if project.name != existing["name"]:
        name_taken = await db.get_project_by_name(project.name)
        if name_taken:
            raise HTTPException(status_code=409, detail="Project with this name already exists")

    updated = await db.update_project(
        project_id,
        name=project.name,
        display_name=project.display_name,
        description=project.description,
    )
    return _project_from_row(updated)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    request: Request,
    db: Database = Depends(get_db),
):
    current_user = await require_auth(request, db)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete projects")

    existing = await db.get_project(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    # Block deletion if project has skills
    skill_count = await db.count_skills_in_project(project_id)
    if skill_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete project with {skill_count} skills. Remove all skills first.",
        )

    await db.delete_project(project_id)
    return None
