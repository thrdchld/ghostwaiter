from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import settings


ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
SCHEMA_VERSION = 1


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_id(value: str, label: str = "id") -> str:
    if not ID_PATTERN.fullmatch(value):
        raise ValueError(f"{label} tidak valid")
    return value


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class JsonStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.data_dir
        self.lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        for path in (
            self.root / "system",
            self.root / "workspaces",
            self.root / "cache",
            self.root / "queue",
            self.root / "snapshots",
            self.root / "archive",
        ):
            path.mkdir(parents=True, exist_ok=True)

        timestamp = now_iso()
        self.ensure_json(
            self.root / "system" / "settings.json",
            {
                "schema_version": SCHEMA_VERSION,
                "active_workspace": "writing",
                "theme": "auto",
                "sync_status": "idle",
                "last_sync": "",
            },
        )
        self.ensure_json(
            self.root / "system" / "models.json",
            {
                "schema_version": SCHEMA_VERSION,
                "default_model": settings.default_model,
                "fallback_models": list(settings.fallback_models),
            },
        )
        self.ensure_json(
            self.root / "system" / "workspaces.json",
            {
                "schema_version": SCHEMA_VERSION,
                "default_workspace": "writing",
                "items": [
                    {
                        "id": "writing",
                        "name": "Writing",
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                ],
            },
        )
        self.ensure_json(
            self.root / "queue" / "pending_sync.json",
            {"schema_version": SCHEMA_VERSION, "items": []},
        )
        self.ensure_json(
            self.root / "snapshots" / "manifest.json",
            {"schema_version": SCHEMA_VERSION, "items": []},
        )
        self.ensure_workspace("writing", "Writing")

    def read_json(self, path: Path, default: Any | None = None) -> Any:
        with self.lock:
            if not path.exists():
                if default is None:
                    raise FileNotFoundError(path)
                return default
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)

    def write_json(self, path: Path, data: Any) -> None:
        with self.lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def ensure_json(self, path: Path, data: Any) -> None:
        if not path.exists():
            self.write_json(path, data)

    def workspace_path(self, workspace_id: str) -> Path:
        return self.root / "workspaces" / safe_id(workspace_id, "workspace_id")

    def ensure_workspace(self, workspace_id: str, name: str | None = None) -> Path:
        workspace_id = safe_id(workspace_id, "workspace_id")
        root = self.workspace_path(workspace_id)
        for folder in (
            "drafts",
            "chats",
            "brain",
            "references",
            "summary",
            "settings",
            "learning/revision_pairs",
            "learning/raw_writing",
            "learning/chat_patterns",
        ):
            (root / folder).mkdir(parents=True, exist_ok=True)
        self.ensure_json(root / "brain" / "style_profile.json", {"schema_version": 1, "rules": []})
        self.ensure_json(root / "brain" / "thinking_profile.json", {"schema_version": 1, "patterns": []})
        self.ensure_json(root / "brain" / "memory.json", {"schema_version": 1, "items": []})
        self.ensure_json(root / "brain" / "rules.json", {"schema_version": 1, "max_rules": 100, "items": []})
        self.ensure_json(root / "brain" / "conversation_memory.json", {"schema_version": 1, "items": []})
        self.ensure_json(root / "brain" / "learning_proposals.json", {"schema_version": 1, "items": []})
        self.ensure_json(
            root / "summary" / "workspace_summary.json",
            {"schema_version": 1, "content": "", "updated_at": ""},
        )
        return root

    def active_workspace(self) -> str:
        data = self.read_json(self.root / "system" / "settings.json")
        return data.get("active_workspace", "writing")

    def set_active_workspace(self, workspace_id: str) -> None:
        safe_id(workspace_id, "workspace_id")
        known = {item["id"] for item in self.list_workspaces()}
        if workspace_id not in known:
            raise KeyError("Workspace tidak ditemukan")
        data = self.read_json(self.root / "system" / "settings.json")
        data["active_workspace"] = workspace_id
        self.write_json(self.root / "system" / "settings.json", data)

    def list_workspaces(self) -> list[dict[str, Any]]:
        data = self.read_json(self.root / "system" / "workspaces.json")
        return data.get("items", [])

    def create_workspace(self, name: str) -> dict[str, Any]:
        clean_name = " ".join(name.split()).strip()
        if not clean_name or len(clean_name) > 60:
            raise ValueError("Nama workspace harus 1-60 karakter")
        base = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-") or "workspace"
        workspace_id = base[:48]
        existing = {item["id"] for item in self.list_workspaces()}
        while workspace_id in existing:
            workspace_id = f"{base[:40]}-{uuid4().hex[:6]}"
        timestamp = now_iso()
        item = {"id": workspace_id, "name": clean_name, "created_at": timestamp, "updated_at": timestamp}
        registry_path = self.root / "system" / "workspaces.json"
        registry = self.read_json(registry_path)
        registry["items"].append(item)
        self.ensure_workspace(workspace_id, clean_name)
        self.write_json(registry_path, registry)
        return item

    def list_entities(self, workspace_id: str, folder: str) -> list[dict[str, Any]]:
        path = self.workspace_path(workspace_id) / folder
        items = []
        for file_path in path.glob("*.json"):
            try:
                items.append(self.read_json(file_path))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(items, key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)

    def get_entity(self, workspace_id: str, folder: str, entity_id: str) -> dict[str, Any]:
        path = self.workspace_path(workspace_id) / folder / f"{safe_id(entity_id)}.json"
        return self.read_json(path)

    def save_entity(self, workspace_id: str, folder: str, entity: dict[str, Any]) -> dict[str, Any]:
        entity_id = safe_id(entity["id"])
        entity.setdefault("schema_version", SCHEMA_VERSION)
        path = self.workspace_path(workspace_id) / folder / f"{entity_id}.json"
        self.write_json(path, entity)
        self.enqueue_sync(
            folder.split("/")[0],
            workspace_id,
            {"id": entity_id, "updated_at": entity.get("updated_at", entity.get("created_at", now_iso()))},
        )
        return entity

    def delete_entity(self, workspace_id: str, folder: str, entity_id: str) -> None:
        path = self.workspace_path(workspace_id) / folder / f"{safe_id(entity_id)}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        archive = self.root / "archive" / folder.split("/")[0] / workspace_id
        archive.mkdir(parents=True, exist_ok=True)
        shutil.move(path, archive / f"{entity_id}_{int(datetime.now().timestamp())}.json")
        self.enqueue_sync(f"{folder}:delete", workspace_id, {"id": entity_id})

    def permanently_delete_entity(self, workspace_id: str, folder: str, entity_id: str) -> None:
        path = self.workspace_path(workspace_id) / folder / f"{safe_id(entity_id)}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        backup = self.root / "archive" / "deleted" / folder.split("/")[0] / workspace_id
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup / f"{entity_id}_{int(datetime.now().timestamp())}.json")
        path.unlink()
        self.enqueue_sync(f"{folder}:purge", workspace_id, {"id": entity_id})

    def enqueue_sync(self, item_type: str, workspace_id: str, payload: dict[str, Any]) -> None:
        queue_path = self.root / "queue" / "pending_sync.json"
        queue = self.read_json(queue_path)
        queue["items"].append(
            {
                "id": new_id("sync"),
                "type": item_type,
                "workspace": workspace_id,
                "payload": payload,
                "created_at": now_iso(),
            }
        )
        queue["items"] = queue["items"][-500:]
        self.write_json(queue_path, queue)

    def create_snapshot(self) -> dict[str, Any]:
        snapshot_id = datetime.now(UTC).strftime("snapshot_%Y_%m_%d_%H%M%S")
        zip_path = self.root / "snapshots" / f"{snapshot_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in self.root.rglob("*"):
                if not path.is_file() or path == zip_path or "snapshots" in path.relative_to(self.root).parts:
                    continue
                archive.write(path, path.relative_to(self.root))
        entry = {
            "id": snapshot_id,
            "file": zip_path.name,
            "created_at": now_iso(),
            "workspace_count": len(self.list_workspaces()),
            "size": zip_path.stat().st_size,
        }
        manifest_path = self.root / "snapshots" / "manifest.json"
        manifest = self.read_json(manifest_path)
        manifest["items"].insert(0, entry)
        self.write_json(manifest_path, manifest)
        return entry

    def snapshot_path(self, snapshot_id: str) -> Path:
        entry = next(
            (item for item in self.read_json(self.root / "snapshots" / "manifest.json")["items"] if item["id"] == snapshot_id),
            None,
        )
        if not entry:
            raise FileNotFoundError(snapshot_id)
        return self.root / "snapshots" / entry["file"]


store = JsonStore()
