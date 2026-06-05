from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .config import StorageConfig
from .interfaces import LocalVectorIndex
from .objects import LocalFileObjectStore
from .paths import DEFAULT_PLUGIN_NAME, PaperOSPaths
from .sqlite.repository import SQLitePaperRepository
from .vector import LanceDBVectorIndex

if TYPE_CHECKING:
    from ..config import PaperOSConfig


@dataclass
class PaperOSStorageContext:
    cfg: StorageConfig
    paths: PaperOSPaths
    repository: SQLitePaperRepository
    object_store: LocalFileObjectStore
    vector_index: LocalVectorIndex

    async def aclose(self) -> None:
        await self.repository.aclose()


async def create_storage_context(
    cfg: "PaperOSConfig | Any",
    *,
    plugin_name: str = DEFAULT_PLUGIN_NAME,
) -> PaperOSStorageContext:
    storage_cfg = getattr(cfg, "storage", StorageConfig())
    paths = PaperOSPaths.from_config(storage_cfg, plugin_name=plugin_name)
    paths.ensure_dirs()
    repo = SQLitePaperRepository(paths.database_path, storage_cfg)
    if storage_cfg.auto_init:
        await repo.initialize()
    object_store = LocalFileObjectStore(paths.object_dir, paths.tmp_dir)
    vector_index = _create_vector_index(storage_cfg, paths)
    return PaperOSStorageContext(
        cfg=storage_cfg,
        paths=paths,
        repository=repo,
        object_store=object_store,
        vector_index=vector_index,
    )


def _create_vector_index(storage_cfg: StorageConfig, paths: PaperOSPaths) -> LocalVectorIndex:
    if storage_cfg.vector_backend != "lancedb":
        raise ValueError(f"Unsupported storage.vector_backend: {storage_cfg.vector_backend}")
    return LanceDBVectorIndex(
        paths.index_dir / "lancedb",
        table_name=storage_cfg.vector_table_name,
    )
