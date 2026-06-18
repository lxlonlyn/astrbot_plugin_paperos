from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UploadedPdfRef:
    name: str
    source_path: Path
    size_bytes: int


def extract_local_pdf_from_event(event: Any) -> UploadedPdfRef | None:
    """Return a local PDF file component from an AstrBot message event.

    This probe intentionally supports only local file paths exposed by the
    platform. It does not download URL-only file messages.
    """

    for comp in _message_components(event):
        candidate = _component_local_path(comp)
        if not candidate:
            continue

        path = Path(candidate)
        if not path.exists() or not path.is_file():
            continue
        if path.suffix.lower() != ".pdf":
            continue

        size = path.stat().st_size
        if size <= 0:
            continue

        return UploadedPdfRef(
            name=_component_name(comp) or path.name,
            source_path=path.resolve(),
            size_bytes=size,
        )
    return None


def event_has_file_message(event: Any) -> bool:
    for comp in _message_components(event):
        if _looks_like_file_component(comp):
            return True
    return False


def copy_pdf_to_upload_tmp(
    ref: UploadedPdfRef,
    *,
    tmp_dir: Path,
    max_size_mb: int,
) -> Path:
    max_bytes = max_size_mb * 1024 * 1024
    if ref.size_bytes > max_bytes:
        raise ValueError(f"PDF 文件过大：{ref.size_bytes} bytes > {max_bytes} bytes")

    upload_dir = tmp_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{uuid.uuid4().hex}.pdf"
    shutil.copy2(ref.source_path, dest)
    return dest.resolve()


def _message_components(event: Any) -> list[Any]:
    message_obj = getattr(event, "message_obj", None)
    message = getattr(message_obj, "message", None)
    if message is not None:
        return list(message)

    get_messages = getattr(event, "get_messages", None)
    if callable(get_messages):
        try:
            return list(get_messages())
        except Exception:
            return []
    return []


def _component_local_path(comp: Any) -> str | None:
    for attr in ("file", "path", "local_path"):
        value = getattr(comp, attr, None)
        if isinstance(value, str) and value.strip():
            if _is_remote(value):
                continue
            return value.strip()
    file_ = getattr(comp, "file_", None)
    if isinstance(file_, str) and file_.strip():
        if _is_remote(file_):
            return None
        return file_.strip()
    return None


def _component_name(comp: Any) -> str | None:
    value = getattr(comp, "name", None)
    return value if isinstance(value, str) and value.strip() else None


def _looks_like_file_component(comp: Any) -> bool:
    type_value = getattr(comp, "type", None)
    if str(type_value).lower().endswith("file"):
        return True
    return any(hasattr(comp, attr) for attr in ("file", "file_", "path", "local_path", "url"))


def _is_remote(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")
