"""Marketplace source admin endpoints (U4, R1/R2/R9/R10)."""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from skillhub.api.deps import get_db, get_storage, require_auth
from skillhub.database import Database
from skillhub.marketplace.fetch import fetch_checkout
from skillhub.marketplace.models import FetchError, ParseError, ParseResult, SourceSpec
from skillhub.marketplace.parse import parse_checkout
from skillhub.marketplace.sync import SyncReport, sync_source
from skillhub.models import (
    MarketplaceSkillResponse,
    MarketplaceSourceCreate,
    MarketplaceSourceResponse,
    MarketplaceSourceUpdate,
)
from skillhub.storage import SkillStorage

router = APIRouter(prefix="/api/marketplaces", tags=["marketplaces"])

_FETCH_TIMEOUT_SECONDS = 120


def _source_from_row(row: dict, imported_skill_count: int = 0) -> MarketplaceSourceResponse:
    return MarketplaceSourceResponse(
        id=row["id"],
        name=row["name"],
        location=row["location"],
        source_ref=row.get("source_ref"),
        project=row.get("project_id"),
        sync_interval_minutes=row.get("sync_interval_minutes") or 0,
        enabled=row.get("enabled", 1),
        last_revision=row.get("last_revision"),
        last_error=row.get("last_error"),
        last_sync_report=row.get("last_sync_report"),
        last_synced_at=row.get("last_synced_at"),
        imported_skill_count=imported_skill_count,
    )


async def _count_imported(db: Database, source_id: str) -> int:
    return len(await db.list_skills_for_source(source_id))


def _validate_location(location: str) -> None:
    from skillhub.marketplace.fetch import normalize_location

    try:
        normalize_location(location)
    except FetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _fetch_and_parse(source: dict) -> tuple[Optional[ParseResult], str, Optional[str]]:
    """Fetch + parse in a worker thread; returns (result, revision, error)."""
    spec = SourceSpec(location=source["location"], ref=source.get("source_ref"))
    try:
        def _run():
            with fetch_checkout(spec) as checkout:
                revision = _checkout_revision(checkout)
                result = parse_checkout(checkout, revision)
                return result, revision

        return (*await run_in_threadpool(_run), None)
    except (FetchError, ParseError) as exc:
        return None, source.get("last_revision") or "", str(exc)


def _checkout_revision(checkout) -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=checkout,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


@router.get("", response_model=list[MarketplaceSourceResponse])
async def list_sources(
    request: Request,
    db: Database = Depends(get_db),
):
    await require_auth(request, db)
    rows = await db.list_marketplace_sources()
    return [
        _source_from_row(row, await _count_imported(db, row["id"])) for row in rows
    ]


@router.get("/{source_id}", response_model=MarketplaceSourceResponse)
async def get_source(
    source_id: str,
    request: Request,
    db: Database = Depends(get_db),
):
    await require_auth(request, db)
    row = await db.get_marketplace_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="Marketplace source not found")
    return _source_from_row(row, await _count_imported(db, source_id))


@router.get("/{source_id}/skills", response_model=list[MarketplaceSkillResponse])
async def list_source_skills(
    source_id: str,
    request: Request,
    db: Database = Depends(get_db),
):
    await require_auth(request, db)
    if not await db.get_marketplace_source(source_id):
        raise HTTPException(status_code=404, detail="Marketplace source not found")
    return [
        MarketplaceSkillResponse(
            id=s["id"],
            name=s["name"],
            upstream_path=s.get("upstream_path"),
            upstream_version=s.get("upstream_version"),
            upstream_revision=s.get("upstream_revision"),
            upstream_status=s.get("upstream_status"),
        )
        for s in await db.list_skills_for_source(source_id)
    ]


@router.post("", response_model=MarketplaceSourceResponse, status_code=201)
async def create_source(
    request: Request,
    payload: MarketplaceSourceCreate,
    db: Database = Depends(get_db),
):
    current_user = await require_auth(request, db)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage marketplaces")

    if await db.get_marketplace_source_by_name(payload.name):
        raise HTTPException(status_code=409, detail="Marketplace source name already exists")
    _validate_location(payload.location)

    project_id = None
    if payload.project:
        proj = await db.get_project_by_name(payload.project)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project '{payload.project}' not found")
        project_id = proj["id"]

    row = await db.create_marketplace_source(
        name=payload.name,
        location=payload.location,
        source_ref=payload.source_ref,
        project_id=project_id,
        sync_interval_minutes=payload.sync_interval_minutes,
        enabled=payload.enabled,
    )
    return _source_from_row(row)


@router.patch("/{source_id}", response_model=MarketplaceSourceResponse)
async def update_source(
    source_id: str,
    payload: MarketplaceSourceUpdate,
    request: Request,
    db: Database = Depends(get_db),
):
    current_user = await require_auth(request, db)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage marketplaces")

    row = await db.get_marketplace_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="Marketplace source not found")

    updates = {}
    if payload.location is not None:
        _validate_location(payload.location)
        updates["location"] = payload.location
    if payload.source_ref is not None:
        updates["source_ref"] = payload.source_ref
    if payload.sync_interval_minutes is not None:
        updates["sync_interval_minutes"] = payload.sync_interval_minutes
    if payload.enabled is not None:
        updates["enabled"] = payload.enabled
    if payload.project is not None:
        proj = await db.get_project_by_name(payload.project)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project '{payload.project}' not found")
        updates["project_id"] = proj["id"]

    updated = await db.update_marketplace_source(source_id, **updates)
    return _source_from_row(updated, await _count_imported(db, source_id))


@router.delete("/{source_id}")
async def delete_source(
    source_id: str,
    request: Request,
    db: Database = Depends(get_db),
    storage: SkillStorage = Depends(get_storage),
):
    current_user = await require_auth(request, db)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage marketplaces")

    row = await db.get_marketplace_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="Marketplace source not found")

    imported = await db.list_skills_for_source(source_id)
    for skill in imported:
        async with storage.lock("skill:" + skill["id"]):
            storage.delete_skill(skill["id"], skill.get("project_id"))
            await db.delete_skill(skill["id"])
    removed = await db.delete_skills_by_source(source_id)
    await db.delete_marketplace_source(source_id)
    return {"removed_skills": removed}


@router.post("/{source_id}/sync")
async def sync(
    source_id: str,
    request: Request,
    db: Database = Depends(get_db),
    storage: SkillStorage = Depends(get_storage),
):
    current_user = await require_auth(request, db)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage marketplaces")

    row = await db.get_marketplace_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="Marketplace source not found")

    result, revision, error = await _fetch_and_parse(row)
    report: SyncReport = await sync_source(db, storage, row, result, revision, error=error)
    return report.to_dict()


# --- Interval sync task (KTD6, R9) ---


async def sync_due_sources(db: Database, storage: SkillStorage) -> int:
    """Sync every enabled source whose interval has elapsed. Returns count."""
    now_rows = await db.list_marketplace_sources()
    count = 0
    for row in now_rows:
        interval = row.get("sync_interval_minutes") or 0
        if not row.get("enabled") or interval <= 0:
            continue
        last = row.get("last_synced_at")
        if last:
            from datetime import UTC, datetime

            elapsed = (datetime.now(UTC) - datetime.fromisoformat(last)).total_seconds()
            if elapsed < interval * 60:
                continue
        result, revision, error = await _fetch_and_parse(row)
        await sync_source(db, storage, row, result, revision, error=error)
        count += 1
    return count


def start_interval_task(app, db: Database, storage: SkillStorage) -> None:
    """Attach the KTD6 periodic sync task to the app lifespan (started unconditionally)."""

    async def _loop():
        while True:
            try:
                await sync_due_sources(db, storage)
            except Exception:  # noqa: BLE001 — the loop must survive any sync failure
                pass
            await asyncio.sleep(60)

    app.state.marketplace_interval_task = asyncio.create_task(_loop())


def stop_interval_task(app) -> None:
    task = getattr(app.state, "marketplace_interval_task", None)
    if task:
        task.cancel()
