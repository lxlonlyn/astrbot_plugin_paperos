# Storage Configuration

## 推荐默认目录

默认使用 AstrBot 插件数据目录：

```text
AstrBot/
  data/
    plugin_data/
      astrbot_plugin_paperos/
        paperos.sqlite3
        objects/
          pdf/
          markdown/
          parsed/
          json/
        tmp/
        indexes/
          fts/
          vector/
```

不要把数据库和对象文件放在插件源码目录下。源码目录可能会被 git pull、重装、容器重建影响。

## _conf_schema.json 推荐配置

```json
"storage": {
  "type": "object",
  "description": "PaperOS 本地数据库与对象存储",
  "items": {
    "enabled": {
      "type": "bool",
      "description": "启用本地 SQLite 存储",
      "default": true
    },
    "root_dir": {
      "type": "string",
      "description": "PaperOS 数据根目录。留空则使用 AstrBot data/plugin_data/<plugin_name>，不要使用插件源码目录",
      "default": ""
    },
    "database_path": {
      "type": "string",
      "description": "SQLite 数据库文件路径。留空则为 root_dir/paperos.sqlite3",
      "default": ""
    },
    "object_dir": {
      "type": "string",
      "description": "PDF、解析结果等大文件目录。留空则为 root_dir/objects",
      "default": ""
    },
    "auto_init": {
      "type": "bool",
      "description": "插件启动时自动初始化目录和数据库 schema",
      "default": true
    },
    "sqlite_journal_mode": {
      "type": "string",
      "description": "SQLite journal mode",
      "default": "WAL",
      "options": ["WAL", "DELETE"]
    },
    "sqlite_synchronous": {
      "type": "string",
      "description": "SQLite synchronous 模式",
      "default": "NORMAL",
      "options": ["NORMAL", "FULL", "OFF"]
    },
    "sqlite_busy_timeout_ms": {
      "type": "int",
      "description": "SQLite busy timeout，毫秒",
      "default": 5000
    }
  }
}
```

## 推荐默认值

```json
{
  "storage": {
    "enabled": true,
    "root_dir": "",
    "database_path": "",
    "object_dir": "",
    "auto_init": true,
    "sqlite_journal_mode": "WAL",
    "sqlite_synchronous": "NORMAL",
    "sqlite_busy_timeout_ms": 5000
  }
}
```

## 是否需要外置数据库

第一阶段不需要。目标规模 5k 篇论文时，SQLite + 本地对象文件足够作为 storage 默认后端。

API embedding provider 属于 RAG 配置，不属于 storage 配置。storage 只保存 embedding/vector/index 的持久化结果或状态。

本地向量索引后续默认放在 `root_dir/indexes/vector/`。SQLite 仍然是 paper、object、chunk、job、index status 的 source of truth；向量库只是可重建索引文件，不应放在插件源码目录下。

后续如果需要多人协作、远程同步、跨设备写入，再考虑 PostgreSQL / S3 / Qdrant / Neo4j 等外部服务。
