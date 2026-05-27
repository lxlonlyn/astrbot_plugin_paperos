# PaperOS Ingest：AI Context

Ingest 不再作为 PaperOS 的顶层模块规划。本文档仅保留为过渡说明：入库应是 command/facade/workflow，组合 `search -> storage -> rag`，而不是新增一个需要长期维护的核心模块。

## 职责

- 调用 `PaperSearchService.search()` 获取候选。
- 根据 `PaperSearchResult.selected` 或用户确认决定入库对象。
- 把 search DTO 转成 storage DTO 并写入 storage。
- 归档 searcher 已验证的本地 PDF。
- 触发 RAG 解析、chunk、embedding、index workflow。

## 不负责

- 实现 CORE/OpenAlex/Crossref provider。
- 直接写 SQLite SQL。
- 直接实现 object store。
- 直接实现 RAG retrieval。
- 成为新的顶层数据模块。

## 推荐第一阶段流程

```text
/paperos add <query>
  ↓
search_service.search(query, need_fulltext=True)
  ↓
choose selected candidate
  ↓
library.import_search_candidate(candidate)
  ↓
rag indexing workflow
  ↓
return paper_id + queued parse status
```
