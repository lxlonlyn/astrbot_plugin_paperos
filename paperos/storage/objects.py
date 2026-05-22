from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .ids import new_id


@dataclass(frozen=True)
class StoredObject:
    id: str
    kind: str
    storage_key: str
    path: Path
    sha256: str
    size_bytes: int
    mime_type: str | None = None
    suffix: str | None = None


class LocalFileObjectStore:
    """Content-addressed local blob store with independent object ids.

    sha256 is only used for file dedup/integrity. The database object id remains
    independent so a paper/version can safely change files over time.
    """

    def __init__(self, object_dir: Path, tmp_dir: Path):
        self.object_dir = object_dir
        self.tmp_dir = tmp_dir
        self.object_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    async def put_bytes(
        self,
        data: bytes,
        *,
        kind: str,
        suffix: str | None = None,
        mime_type: str | None = None,
        object_id: str | None = None,
    ) -> StoredObject:
        obj_id = object_id or new_id("obj")
        sha256 = hashlib.sha256(data).hexdigest()
        suffix = self._normalize_suffix(suffix)
        storage_key = self._storage_key(kind=kind, sha256=sha256, suffix=suffix)
        final_path = self.object_dir / storage_key
        final_path.parent.mkdir(parents=True, exist_ok=True)

        if not final_path.exists():
            tmp_path = self.tmp_dir / f"{obj_id}.part"
            with tmp_path.open("wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, final_path)

        return StoredObject(
            id=obj_id,
            kind=kind,
            storage_key=storage_key,
            path=final_path,
            sha256=sha256,
            size_bytes=len(data),
            mime_type=mime_type,
            suffix=suffix,
        )

    async def put_file(
        self,
        source_path: Path,
        *,
        kind: str,
        suffix: str | None = None,
        mime_type: str | None = None,
        object_id: str | None = None,
    ) -> StoredObject:
        source_path = Path(source_path)
        data = source_path.read_bytes()
        return await self.put_bytes(
            data,
            kind=kind,
            suffix=suffix or source_path.suffix,
            mime_type=mime_type,
            object_id=object_id,
        )

    def resolve_path(self, storage_key: str) -> Path:
        candidate = (self.object_dir / storage_key).resolve()
        root = self.object_dir.resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError(f"unsafe storage_key outside object_dir: {storage_key!r}")
        return candidate

    def exists(self, storage_key: str) -> bool:
        return self.resolve_path(storage_key).exists()

    def _storage_key(self, *, kind: str, sha256: str, suffix: str | None) -> str:
        clean_kind = kind.strip().lower().replace("/", "_") or "blob"
        ext = suffix or ""
        return f"{clean_kind}/{sha256[:2]}/{sha256[:4]}/{sha256}{ext}"

    def _normalize_suffix(self, suffix: str | None) -> str:
        if not suffix:
            return ""
        suffix = suffix.strip().lower()
        if not suffix:
            return ""
        return suffix if suffix.startswith(".") else f".{suffix}"
