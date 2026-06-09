# PaperOS Workflows：AI Context

本文件是给 ChatGPT / 代码智能体优先阅读的 workflow 层黑盒上下文。

## 当前任务边界

`paperos/workflows/` 是跨模块 pipeline/orchestration 层，不是新的核心数据模块。PaperOS 稳定核心模块只有 `search`、`storage`、`rag`；不要为复杂操作新增或恢复 `runtime`、`reasoning`、`ingest` 顶层模块。

Workflow 可以组合：

- `search`: 在线发现与临时 verified PDF；
- `storage`: metadata upsert、object archival、document processing jobs；
- `rag`: embedding、vector index、retrieval jobs；
- `storage`: job/index status 和可查询结果。

Workflow 不拥有：

- search ranking；
- storage schema；
- GROBID/parser 实现；
- embedding provider 实现；
- RAG retrieval 算法。

任何核心模块都不应反向 import workflow。

## 当前 workflow

- `SearchStorageImportWorkflow`
  - 只做 search result -> storage import。
  - 把 `PaperCandidate` 转成 `PaperRecordDraft`。
  - 归档 verified PDF object。
  - 可选入队 `storage_parse_pdf`。

- `PaperDiscoveryWorkflow`
  - 用户级 pipeline。
  - 同步执行 search、storage import、storage document processing。
  - 当 import result 带有 `parser_run_id` 且调用方注入 `rag_index_service` 时，继续调用 `rag_index_service.index_parser_run(...)`。
  - RAG indexing 成功后标记 `rag_embed_chunks` job done；失败时标记 job failed 和 `index_status=failed`，但不回滚 search/storage。
  - `/paperos search` command 使用这个 pipeline；`paperos_search_paper` LLM tool 仍只返回 search result，不做隐式入库/index。

## 依赖方向

```text
AstrBot command/tool
  -> paperos.workflows
      -> search
      -> storage
      -> rag
```

```text
search  -X-> workflows
storage -X-> workflows
rag     -X-> workflows
```

## 禁止误解

- 不要新建 `paperos/index` 模块。
- 不要新增 `/paperos index` 指令组来表达 search 后处理。
- 不要把 embedding provider 调用放进 searcher 或 storage。
- 不要让 `SearchStorageImportWorkflow` 代表完整 pipeline；它只做 search result -> storage import。
