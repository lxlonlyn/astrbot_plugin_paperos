from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import StorageConfig

DEFAULT_PLUGIN_NAME = "astrbot_plugin_paperos"


def default_plugin_data_dir(plugin_name: str = DEFAULT_PLUGIN_NAME) -> Path:
    """Return AstrBot's conventional plugin data directory.

    AstrBot v4.9.2+ exposes self.name on Star instances. Pass it from main.py
    when possible. The fallback keeps local tests usable outside AstrBot.
    """

    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore

        return Path(get_astrbot_data_path()) / "plugin_data" / plugin_name
    except Exception:
        return Path.cwd() / "data" / "plugin_data" / plugin_name


@dataclass(frozen=True)
class PaperOSPaths:
    root_dir: Path
    database_path: Path
    object_dir: Path
    tmp_dir: Path
    index_dir: Path
    fts_index_dir: Path
    vector_index_dir: Path

    @classmethod
    def from_config(cls, cfg: StorageConfig, *, plugin_name: str = DEFAULT_PLUGIN_NAME) -> "PaperOSPaths":
        root = Path(cfg.root_dir).expanduser() if cfg.root_dir else default_plugin_data_dir(plugin_name)
        root = root.resolve()
        db_path = Path(cfg.database_path).expanduser().resolve() if cfg.database_path else root / "paperos.sqlite3"
        object_dir = Path(cfg.object_dir).expanduser().resolve() if cfg.object_dir else root / "objects"
        index_dir = root / "indexes"
        return cls(
            root_dir=root,
            database_path=db_path,
            object_dir=object_dir,
            tmp_dir=root / "tmp",
            index_dir=index_dir,
            fts_index_dir=index_dir / "fts",
            vector_index_dir=index_dir / "vector",
        )

    def ensure_dirs(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.object_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.fts_index_dir.mkdir(parents=True, exist_ok=True)
        self.vector_index_dir.mkdir(parents=True, exist_ok=True)
