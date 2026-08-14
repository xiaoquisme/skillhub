"""Configuration loading from ~/.skillhub/config.yaml."""

import os
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """Server configuration."""
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False


class StorageConfig(BaseModel):
    """Storage configuration."""
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".skillhub" / "data")
    skills_dir: Path = Field(default_factory=lambda: Path.home() / ".skillhub" / "skills")


class AdminConfig(BaseModel):
    """Admin user preset configuration."""
    username: str = "admin"
    password_hash: str = ""


class AppConfig(BaseModel):
    """Application configuration."""
    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    registry_url: str = "http://127.0.0.1:8000"
    admin: AdminConfig = Field(default_factory=AdminConfig)
    api_token: str = ""
    default_project: Optional[str] = None


CONFIG_DIR = Path.home() / ".skillhub"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """Load configuration from YAML file, falling back to defaults.
    
    Environment variables override YAML values for Docker deployments:
    - SKILLHUB_DATA_DIR: overrides storage.data_dir
    - SKILLHUB_SKILLS_DIR: overrides storage.skills_dir
    - SKILLHUB_HOST: overrides server.host
    - SKILLHUB_PORT: overrides server.port
    - SKILLHUB_DEFAULT_PROJECT: overrides default_project
    """
    path = config_path or CONFIG_FILE
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        config = AppConfig(**data)
    else:
        config = AppConfig()

    # Environment variable overrides for Docker deployments
    if data_dir := os.environ.get("SKILLHUB_DATA_DIR"):
        config.storage.data_dir = Path(data_dir)
    if skills_dir := os.environ.get("SKILLHUB_SKILLS_DIR"):
        config.storage.skills_dir = Path(skills_dir)
    if host := os.environ.get("SKILLHUB_HOST"):
        config.server.host = host
    if port := os.environ.get("SKILLHUB_PORT"):
        config.server.port = int(port)
    if default_project := os.environ.get("SKILLHUB_DEFAULT_PROJECT"):
        config.default_project = default_project

    return config

def save_config(config: AppConfig, config_path: Optional[Path] = None) -> None:
    """Save configuration to YAML file."""
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump()
    # Convert Path objects to strings for YAML serialization
    data["storage"]["data_dir"] = str(data["storage"]["data_dir"])
    data["storage"]["skills_dir"] = str(data["storage"]["skills_dir"])
    with open(path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)
