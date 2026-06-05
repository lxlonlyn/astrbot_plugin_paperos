# Runtime Configuration

PaperOS 配置应分模块组织，避免所有配置堆在一个平面。

推荐顶层结构：

```text
general
query_analyzer
crawler
core_api
search_policy
storage
rag
```

当前 `_conf_schema.json` 已暴露：

- `general`
- `query_analyzer`
- `crawler`
- `core_api`
- `search_policy`
- `storage`
- `rag`

当前 `PaperOSConfig` 已加载：

- `general`
- `query_analyzer`
- `crawler`
- `core_api`
- `search_policy`
- `storage`
- `rag`

`storage` 和 `rag` 已是顶层配置，接入了 `PaperOSConfig` 和 `_conf_schema.json`。

`rag.embedding_provider_id` 只保存 AstrBot embedding provider 的 id/name。具体 Qwen/OpenAI/其他 embedding provider 的密钥、模型和 endpoint 应在 AstrBot provider 页面配置，PaperOS 不实现这些 provider。

不要为 `ingest` 或 `reasoning` 新增顶层配置，除非它们已经明确收敛为 command/workflow 级能力。文章数据链路应保持在 `search`、`storage`、`rag` 内。

## 原则

- 已实现的模块配置才暴露到 `_conf_schema.json`。
- future backend 可以先写入文档，不一定暴露到用户配置面板。
- storage 默认本地 SQLite。
- embedding provider 配置应归入 rag，不要求本地 GPU。
