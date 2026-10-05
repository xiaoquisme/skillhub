"""Skill CRUD endpoints."""

import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import FileResponse

from skillhub.api.deps import get_db, get_storage, require_auth
from skillhub.database import Database
from skillhub.models import SkillDetail, SkillFileResponse, SkillResponse
from skillhub.storage import SkillStorage

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _skill_from_row(row: dict) -> SkillResponse:
    tags = json.loads(row["tags"]) if row.get("tags") else []
    # Resolve project_id to project name if present
    project_name = row.get("project_name") if "project_name" in row else None
    return SkillResponse(
        id=row["id"],
        name=row["name"],
        display_name=row.get("display_name"),
        description=row.get("description"),
        category=row.get("category"),
        tags=tags,
        author=row.get("author"),
        license=row.get("license"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        published_by=row.get("published_by"),
        download_count=row.get("download_count", 0),
        project=project_name or row.get("project_id"),
    )


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    request: Request,
    q: Optional[str] = Query(None, description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    project: Optional[str] = Query(None, description="Filter by project name"),
    sort: str = Query("updated_at", description="Sort field"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    await require_auth(request, db)

    # Resolve project name to project_id if provided
    project_id = None
    if project:
        proj = await db.get_project_by_name(project)
        if proj:
            project_id = proj["id"]

    skills = await db.list_skills(
        query=q, category=category, project_id=project_id, sort=sort, limit=limit, offset=offset
    )
    return [_skill_from_row(s) for s in skills]


@router.get("/{skill_id}", response_model=SkillDetail)
async def get_skill(skill_id: str, request: Request, db: Database = Depends(get_db)):
    await require_auth(request, db)
    skill = await db.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    files = await db.get_skill_files(skill_id)

    return SkillDetail(
        **_skill_from_row(skill).model_dump(exclude={"file_count"}),
        file_count=len(files),
        files=[
            SkillFileResponse(
                filename=f["filename"],
                content_type=f.get("content_type", "text/markdown"),
                size_bytes=f.get("size_bytes"),
            )
            for f in files
        ],
    )


@router.get("/{skill_id}/files/{filename:path}")
async def download_skill_file(
    skill_id: str,
    filename: str,
    request: Request,
    db: Database = Depends(get_db),
    storage: SkillStorage = Depends(get_storage),
):
    await require_auth(request, db)
    skill = await db.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    project_id = skill.get("project_id")
    file_path = storage.get_skill_file_path(skill_id, filename, project_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")

    # Track download
    await db.increment_download_count(skill_id)

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )


@router.post("", response_model=SkillResponse, status_code=201)
async def publish_skill(
    request: Request,
    name: str = Form(...),
    display_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    license: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
    db: Database = Depends(get_db),
    storage: SkillStorage = Depends(get_storage),
):
    # Require authentication for publishing
    current_user = await require_auth(request, db)
    tags_list = json.loads(tags) if tags else []

    # Resolve project name to project_id
    project_id = None
    if project:
        proj = await db.get_project_by_name(project)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")
        project_id = proj["id"]

    # Validate and read all uploads before changing either metadata or files.
    uploads = []
    try:
        for upload_file in files:
            filename = upload_file.filename or "unnamed"
            storage.validate_filename(filename)
            uploads.append((filename, await upload_file.read(), upload_file.content_type))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Name lock serializes initial upserts; ID lock is shared with bundle/delete.
    async with storage.lock("name:" + json.dumps([project_id, name])):
        existing = await db.get_skill_by_name(name, project_id)
        skill_id = existing["id"] if existing else str(uuid.uuid4())
        async with storage.lock("skill:" + skill_id):
            existing = await db.get_skill(skill_id)
            if existing and current_user["role"] != "admin":
                if existing.get("published_by") != current_user["id"]:
                    raise HTTPException(status_code=403, detail="You can only publish your own skills")
            try:
                for filename, _, _ in uploads:
                    storage._safe_path(skill_id, filename, project_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            previous_files = await db.get_skill_files(skill_id) if existing else []
            with storage.publication_files(skill_id, uploads, project_id):
                try:
                    if existing:
                        await db.update_skill(
                            skill_id, display_name=display_name, description=description,
                            category=category, tags=json.dumps(tags_list), author=author, license=license,
                        )
                    else:
                        await db.create_skill(
                            name=name, display_name=display_name, description=description,
                            category=category, tags=tags_list, author=author, license=license,
                            published_by=current_user["id"], project_id=project_id, skill_id=skill_id,
                        )
                    for filename, content, content_type in uploads:
                        await db.add_skill_file(
                            skill_id=skill_id, filename=filename,
                            content_type=content_type or "application/octet-stream", size_bytes=len(content),
                        )
                    updated = await db.get_skill(skill_id)
                    assert updated is not None
                    response = _skill_from_row(updated)
                except BaseException:
                    await db.restore_publication(skill_id, existing, previous_files)
                    raise
            return response


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    request: Request,
    db: Database = Depends(get_db),
    storage: SkillStorage = Depends(get_storage),
):
    # Require authentication for deleting
    current_user = await require_auth(request, db)

    async with storage.lock("skill:" + skill_id):
        skill = await db.get_skill(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        # Ownership check: publishers can only delete their own skills; admin can delete any
        if current_user["role"] != "admin":
            if skill.get("published_by") != current_user["id"]:
                raise HTTPException(status_code=403, detail="You can only delete your own skills")

        project_id = skill.get("project_id")
        storage.delete_skill(skill_id, project_id)
        await db.delete_skill(skill_id)
        return None
