# Storage 模块

Storage 是 PaperOS 的本地事实源。它不联网，不调用 LLM，不调用 embedding provider。

## 职责

- SQLite schema / migration。
- paper metadata、identifier、alias、version、object、fulltext location、job、chunk、index status。
- content-addressed object store。
- 本地去重。
- 为 search 入库和 RAG 索引/检索提供持久化 API。

## 边界

Storage 不应该 import `paperos.search.models`。Search 的候选对象应在上层 facade 转换为 `storage.models.PaperRecordDraft` 后再交给 repository。

```text
search.PaperCandidate
  -> facade/adapter converts
  -> storage.PaperRecordDraft
  -> repository.upsert_paper()
```

Storage 不接受 URL 下载任务，只接受已经存在的本地文件或 bytes。

## 与 RAG

Embedding provider、PDF parser、chunker、retriever 不属于 storage。它们属于 `paperos/rag/`。

```text
rag.parser/chunker/indexer
  -> read object paths from storage
  -> call embedding provider if needed
  -> write chunks/vector metadata/index status through storage APIs
```
