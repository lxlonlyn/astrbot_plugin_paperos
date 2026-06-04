# Discovery Pipeline

`PaperDiscoveryWorkflow` 是用户级论文发现 pipeline。它属于 `paperos/workflows/`，不属于 searcher。

## Goal

把用户的一次请求组织为：

```text
search
  -> storage
  -> storage document processing
  -> rag
  -> storage status
```

## Current API

```python
result = await PaperDiscoveryWorkflow(
    search_service=search_service,
    search_storage=search_storage_workflow,
).discover_and_index(
    query,
    need_fulltext=True,
    auto_import=True,
)
```

返回 `DiscoveryPipelineResult`：

- `search_result`
- `import_summary`
- `storage_parse_job_ids`
- `rag_job_ids`
- `import_error`
- `imported_count`
- `pdf_count`

## Stage Contract

### 1. Search

```text
PaperSearchService.search(query, need_fulltext=True)
```

Search 负责在线发现、临时 PDF 下载和 PDF 验证。Search 不写 storage。

### 2. Storage Import

```text
SearchStorageImportWorkflow.import_search_result(...)
```

Storage import 负责：

- upsert paper metadata；
- archive verified PDF object；
- link object/version/fulltext location；
- enqueue `storage_parse_pdf`。

`SearchStorageImportWorkflow` 的语义到此为止。它不是完整 discovery pipeline。

### 3. Storage Document Processing

```text
storage_parse_pdf job
  -> GROBID/local parser
  -> TEI
  -> normalized document
  -> chunks/FTS
```

即使未来第一版实现同步处理，也应保留 job 状态：

- claim job；
- mark done / failed；
- expose status through `/paperos storage status` and `/paperos storage info`。

### 4. RAG Embedding / Vector Index

```text
rag_embed_chunks job
  -> embedding provider
  -> vector index
  -> index_status
```

RAG 不解析 PDF，不下载 URL，不写 search candidates。

### 5. Storage Status

Storage 是 pipeline 状态的查询面：

- paper metadata；
- object link；
- verified PDF status；
- chunks；
- jobs；
- index_status。

## Rules

- Do not put this pipeline inside `paperos/search`.
- Do not let storage/rag import `paperos.workflows`.
- Do not bypass `paper_jobs` for document processing or embedding stages.
- `auto_import=False` means discovery returns search result only.
- `SearchStorageImportWorkflow` remains a small adapter, not the full pipeline.
- Runtime commands may set `ignore_import_errors=True` so a storage failure does not discard the search result.
