from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    configured = os.getenv("DATA_DIR")
    if configured:
        return Path(configured)
    persistent = Path("/data")
    if persistent.exists() and os.access(persistent, os.W_OK):
        return persistent / "ghostwriter"
    return ROOT_DIR / "data"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = _data_dir()
    hf_token: str = os.getenv("HF_TOKEN", "")
    app_password: str = os.getenv("APP_PASSWORD", "")
    session_secret: str = os.getenv("SESSION_SECRET", os.getenv("APP_PASSWORD", "dev-secret-change-me"))
    default_model: str = os.getenv("HF_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
    fallback_models: tuple[str, ...] = tuple(
        model.strip()
        for model in os.getenv(
            "HF_FALLBACK_MODELS",
            "Qwen/Qwen3-8B,mistralai/Mistral-7B-Instruct-v0.3",
        ).split(",")
        if model.strip()
    )
    inference_provider: str = os.getenv("HF_INFERENCE_PROVIDER", "auto")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_repo: str = os.getenv("GITHUB_BACKUP_REPO", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    sync_debounce_seconds: int = int(os.getenv("SYNC_DEBOUNCE_SECONDS", "45"))


settings = Settings()

