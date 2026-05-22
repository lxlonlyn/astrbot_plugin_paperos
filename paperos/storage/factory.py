from __future__ import annotations

from dataclasses import dataclass

from ..config import PaperOSConfig

from .config import StorageConfig
from .objects import LocalFileObjectStore
from .paths import DEFAULT_PLUGIN_NAME, PaperOSPaths
from .sqlite.repository import SQLitePaperRepository


@dataclass
class PaperOSStorageContext:
    cfg: StorageConfig
    paths: PaperOSPaths
    repository: SQLitePaperRepository
    object_store: LocalFileObjectStore

    async def aclose(self) -> None:
        await self.repository.aclose()


async def create_storage_context(
    cfg: PaperOSConfig,
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
    return PaperOSStorageContext(
        cfg=storage_cfg,
        paths=paths,
        repository=repo,
        object_store=object_store,
    )
