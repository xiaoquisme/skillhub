"""Pydantic models for SkillHub."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# --- Project models ---

class ProjectBase(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectResponse(ProjectBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Skill models ---

class SkillBase(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    author: Optional[str] = None
    license: Optional[str] = None
    project: Optional[str] = None


class SkillCreate(SkillBase):
    pass


class SkillResponse(SkillBase):
    id: str
    created_at: datetime
    updated_at: datetime
    published_by: Optional[str] = None
    file_count: int = 0
    download_count: int = 0


class SkillDetail(SkillResponse):
    files: list["SkillFileResponse"] = Field(default_factory=list)
    upstream: Optional["SkillUpstream"] = None


class SkillUpstream(BaseModel):
    """Additive provenance for marketplace-imported skills (U4)."""

    source: Optional[str] = None
    path: Optional[str] = None
    version: Optional[str] = None
    revision: Optional[str] = None
    status: Optional[str] = None


class SkillFileResponse(BaseModel):
    filename: str
    content_type: str = "text/markdown"
    size_bytes: Optional[int] = None


# --- User models ---

class UserBase(BaseModel):
    username: str
    role: str = "viewer"


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    created_at: datetime
    updated_at: datetime


class UserPasswordChange(BaseModel):
    old_password: str
    new_password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminPasswordReset(BaseModel):
    new_password: str


# --- Marketplace models ---

class MarketplaceSourceBase(BaseModel):
    name: str
    location: str
    source_ref: Optional[str] = None
    project: Optional[str] = None
    sync_interval_minutes: int = 0
    enabled: int = 1


class MarketplaceSourceCreate(MarketplaceSourceBase):
    pass


class MarketplaceSourceUpdate(BaseModel):
    location: Optional[str] = None
    source_ref: Optional[str] = None
    project: Optional[str] = None
    sync_interval_minutes: Optional[int] = None
    enabled: Optional[int] = None


class MarketplaceSourceResponse(BaseModel):
    id: str
    name: str
    location: str
    source_ref: Optional[str] = None
    project: Optional[str] = None
    sync_interval_minutes: int = 0
    enabled: int = 1
    last_revision: Optional[str] = None
    last_error: Optional[str] = None
    last_sync_report: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    imported_skill_count: int = 0


class MarketplaceSkillResponse(BaseModel):
    id: str
    name: str
    upstream_path: Optional[str] = None
    upstream_version: Optional[str] = None
    upstream_revision: Optional[str] = None
    upstream_status: Optional[str] = None


SkillDetail.model_rebuild()
