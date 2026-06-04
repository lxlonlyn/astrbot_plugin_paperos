# PaperOS Ingest：AI Context

Ingest 不再作为 PaperOS 的顶层模块规划。本文档仅保留为过渡说明：入库应迁移到 `docs/modules/workflows/` 描述的 command/facade/workflow，组合 `search -> storage document processing -> rag`，而不是新增一个需要长期维护的核心模块。

## 职责

- 调用 `PaperSearchService.search()` 获取候选，并在同一次 workflow 中消费这份 `PaperSearchResult`。
- 根据 `PaperSearchResult.selected` 或用户确认决定入库对象；不要通过另一个 `/add` 命令再次 search。
- 把 search DTO 转成 storage DTO 并写入 storage。
- 归档 searcher 已验证的本地 PDF。
- 触发 storage document processing：PDF -> TEI -> normalized document -> chunks / FTS。
- 后续由 RAG 触发 embedding/vector index/retrieval workflow。

## 不负责

- 实现 CORE/OpenAlex/Crossref provider。
- 直接写 SQLite SQL。
- 直接实现 object store。
- 直接实现 RAG retrieval。
- 成为新的顶层数据模块。

## 推荐第一阶段流程

```text
/paperos search <query>
  ↓
search_service.search(query, need_fulltext=True)
  ↓
choose selected candidate(s)
  ↓
SearchStorageImportWorkflow.import_search_result(result)
  ↓
storage upsert + object archival + storage_parse_pdf job
  ↓
storage-aware response formatter returns paper_id/object/job status
```
