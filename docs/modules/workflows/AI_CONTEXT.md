# PaperOS Workflows：AI Context

本文件是给 ChatGPT / 代码智能体优先阅读的 workflow 层黑盒上下文。

## 当前任务边界

`paperos/workflows/` 是跨模块 orchestration 层，不是新的核心数据模块。

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
  - 第一阶段同步执行 search 和 storage import。
  - 后续 storage document processing / RAG embedding 通过 job 状态表达。

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
