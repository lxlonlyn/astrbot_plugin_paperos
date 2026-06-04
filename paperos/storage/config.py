from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class StorageConfig:
    """Local storage configuration for PaperOS.

    SQLite is the metadata source of truth. Large blobs such as PDFs, parsed
    markdown/json and future images are stored in the local object directory.
    """

    enabled: bool = True
    root_dir: str = ""
    database_path: str = ""
    object_dir: str = ""
    auto_init: bool = True
    sqlite_timeout_seconds: float = 30.0
    sqlite_busy_timeout_ms: int = 5000
    sqlite_journal_mode: str = "WAL"
    sqlite_synchronous: str = "NORMAL"
    grobid_base_url: str = "http://localhost:8070"
    grobid_timeout_seconds: float = 120.0


def load_storage_config(raw: Mapping[str, Any]) -> StorageConfig:
    section = raw.get("storage", {})
    if not isinstance(section, Mapping):
        section = {}

    return StorageConfig(
        enabled=bool(section.get("enabled", True)),
        root_dir=str(section.get("root_dir", "") or ""),
        database_path=str(section.get("database_path", "") or ""),
        object_dir=str(section.get("object_dir", "") or ""),
        auto_init=bool(section.get("auto_init", True)),
        sqlite_timeout_seconds=float(section.get("sqlite_timeout_seconds", 30.0) or 30.0),
        sqlite_busy_timeout_ms=int(section.get("sqlite_busy_timeout_ms", 5000) or 5000),
        sqlite_journal_mode=str(section.get("sqlite_journal_mode", "WAL") or "WAL").upper(),
        sqlite_synchronous=str(section.get("sqlite_synchronous", "NORMAL") or "NORMAL").upper(),
        grobid_base_url=str(section.get("grobid_base_url", "http://localhost:8070") or "http://localhost:8070").rstrip("/"),
        grobid_timeout_seconds=float(section.get("grobid_timeout_seconds", 120.0) or 120.0),
    )


def ensure_absolute_or_empty(path: str) -> str:
    if not path:
        return ""
    return str(Path(path).expanduser().resolve())
