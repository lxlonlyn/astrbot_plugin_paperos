# PaperOS Ingest：AI Context

Ingest 是未来用于编排论文入库的模块。它连接 search、storage、download、parse、chunk、embedding，但不拥有这些模块的底层实现。

## 职责

- 调用 `PaperSearchService.search()` 获取候选。
- 根据 `PaperSearchResult.selected` 或用户确认决定入库对象。
- 调用 storage 做本地去重和 paper upsert。
- 注册 fulltext location。
- 选择最佳 PDF URL。
- 创建 download / parse / chunk / embed job。
- 推进入库状态机。

## 不负责

- 实现 CORE/OpenAlex/Crossref provider。
- 直接写 SQLite SQL。
- 直接实现 object store。
- 直接实现 RAG retrieval。

## 推荐第一阶段流程

```text
/paperos ingest <query>
  ↓
search_service.search(query, need_fulltext=True)
  ↓
choose selected candidate
  ↓
repo.upsert_candidate(candidate)
  ↓
repo.register_fulltext_locations(candidate.fulltext_locations)
  ↓
repo.enqueue_job(download_pdf)
  ↓
return paper_id + queued status
```
