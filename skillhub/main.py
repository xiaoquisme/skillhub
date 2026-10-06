"""SkillHub FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from skillhub.api.deps import get_config, get_db, get_storage
from skillhub.api.workbench import router as workbench_router
from skillhub.api.skills import router as skills_router
from skillhub.api.auth import router as auth_router
from skillhub.api.users import router as users_router
from skillhub.api.projects import router as projects_router
from skillhub.api.marketplaces import (
    router as marketplaces_router,
    start_interval_task,
    stop_interval_task,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = await get_config()
    db = await get_db(config)
    storage = await get_storage(config)

    # Migrate legacy skill directories to default/ subdirectory
    storage.migrate_legacy_skills()

    # U5: Create admin user from config preset if configured
    if config.admin.password_hash:
        existing_admin = await db.get_user_by_username(config.admin.username)
        if not existing_admin:
            await db.create_user(
                username=config.admin.username,
                password_hash=config.admin.password_hash,
                role="admin",
            )

    # KTD6: interval sync runs unconditionally; it re-checks due sources each
    # tick so sources created after boot are picked up without a restart.
    start_interval_task(app, db, storage)

    yield
    stop_interval_task(app)
    await db.close()


app = FastAPI(
    title="SkillHub",
    description="A lightweight skill registry for Hermes Agent skills",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "skillhub"}

app.include_router(skills_router)
app.include_router(workbench_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(projects_router)
app.include_router(marketplaces_router)


# --- Auth middleware for UI pages ---
# Protects /ui/ pages (except login, static assets) from unauthenticated access.
# Redirects unauthenticated browser requests to the login page.

PUBLIC_UI_PATHS = {"/ui/login.html"}
UI_ASSET_PREFIXES = ("/ui/css/", "/ui/js/", "/ui/locales/")

@app.middleware("http")
async def auth_redirect_middleware(request: Request, call_next):
    path = request.url.path

    # Only apply to /ui/ paths
    if path.startswith("/ui/"):
        # Allow login page and static assets (css, js, locales) without auth
        if path in PUBLIC_UI_PATHS or any(path.startswith(p) for p in UI_ASSET_PREFIXES):
            return await call_next(request)

        # Check for JWT token in cookie (set during login)
        token = request.cookies.get("skillhub_token", "")
        if token:
            # Cookie exists — let the request through (API will validate if needed)
            return await call_next(request)

        # No cookie — redirect to login
        return RedirectResponse(url="/ui/login.html", status_code=302)

    return await call_next(request)


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="static")
