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


SkillDetail.model_rebuild()
