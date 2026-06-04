# Storage 模块

Storage 是 PaperOS 的本地事实源和文档数据处理层。它不联网搜索论文，不调用 LLM，不调用 embedding provider。

## 职责

- SQLite schema / migration。
- paper metadata、identifier、alias、version、object、fulltext location、job、chunk、index status。
- content-addressed object store。
- 本地去重。
- 本地 GROBID/parser 文档处理。
- PDF -> TEI -> normalized document -> chunks / FTS。
- 为 search 入库和 RAG 索引/检索提供持久化 API。

## 边界

Storage 不应该 import `paperos.search.models`。Search 的候选对象应在上层 facade 转换为 `storage.models.PaperRecordDraft` 后再交给 repository。

```text
search.PaperSearchResult / search.PaperCandidate
  -> paperos.workflows.search_storage converts
  -> storage.PaperRecordDraft
  -> repository.upsert_paper()
```

Storage 不接受 URL 下载任务，只接受已经存在的本地文件或 bytes。

search/storage 的组合入口属于 workflow 层，不属于 storage 包内部。正式入口是 `paperos.workflows.search_storage.SearchStorageImportWorkflow`；顶层 `paperos.library` 只保留兼容导出。

## 文档处理边界

GROBID adapter、TEI normalizer、chunker 和 FTS 持久化属于 storage。它们只处理已经归档到 object store 的本地文件，不从 URL 下载 PDF，不做外部论文搜索。

```text
storage object PDF
  -> local GROBID/parser
  -> TEI XML
  -> normalized document
  -> chunks / FTS
```

## 与 RAG

Embedding provider、vector index、retriever、context builder 和 answer/analysis workflow 属于 `paperos/rag/`。

```text
rag.indexer/retriever
  -> read chunks / normalized document from storage
  -> call embedding provider
  -> write vector metadata/index status through storage APIs
```
