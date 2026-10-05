"""Authenticated atomic current bundles for Workbench server consumers."""

import base64
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from skillhub.api.deps import get_db, get_storage, require_auth
from skillhub.database import Database
from skillhub.storage import SkillStorage

router = APIRouter(prefix="/api/workbench/skills", tags=["workbench"])


def _bundle(storage: SkillStorage, skill: dict) -> dict:
    contents = storage.read_bundle_files(skill["id"], skill.get("project_id"))
    files = [
        {
            "path": path,
            "encoding": "base64",
            "content": base64.b64encode(content).decode("ascii"),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, content in sorted(contents.items())
    ]
    digest_input = "".join(file["path"] + "\0" + file["sha256"] + "\0" for file in files)
    return {
        "id": skill["id"],
        "name": skill["name"],
        "description": skill.get("description") or "",
        "files": files,
        "contentDigest": hashlib.sha256(digest_input.encode("utf-8")).hexdigest(),
    }


@router.get("/{skill_id}/bundle")
async def get_bundle(
    skill_id: str,
    request: Request,
    db: Database = Depends(get_db),
    storage: SkillStorage = Depends(get_storage),
):
    await require_auth(request, db)
    async with storage.lock("skill:" + skill_id):
        skill = await db.get_skill(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        try:
            return await run_in_threadpool(_bundle, storage, skill)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
