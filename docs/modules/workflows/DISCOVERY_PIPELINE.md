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
    rag_index_service=rag_index_service,
).discover_and_index(
    query,
    need_fulltext=True,
    auto_import=True,
    search_context=None,
)
```

返回 `DiscoveryPipelineResult`：

- `search_result`
- `import_summary`
- `storage_parse_job_ids`
- `rag_job_ids`
- `rag_index_attempts`
- `import_error`
- `imported_count`
- `pdf_count`
- `rag_index_failed_count`
- `rag_indexed_vector_count`

## Stage Contract

### 1. Search

```text
PaperSearchService.search(query, need_fulltext=True, context=search_context)
```

Search 负责在线发现、临时 PDF 下载和 PDF 验证。Search 不写 storage。
`search_context` 是可选的 `paperos.search.models.SearchContext`，由 workflow
外部或 workflow 调用方提供。Search 只消费这些 hint；RAG/storage 不应被
searcher 反向调用。

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
  -> chunk_embedding_status
  -> index_status
```

`PaperDiscoveryWorkflow` 可以接收可选 `rag_index_service`。当 storage
document processing 已同步完成并在 import summary 中返回 `parser_run_id`
时，workflow 会调用：

```python
await rag_index_service.index_parser_run(item.parser_run_id)
```

这是 `/paperos search` 的后处理，不是新的用户目标，也不需要新增 `index`
模块或指令组。RAG 不解析 PDF，不下载 URL，不写 search candidates。

失败处理必须保守：

- PDF 入库、object archive、parser/chunks/FTS 成功后，不因 embedding 失败回滚；
- `rag_embed_chunks` job 标记 failed；
- paper-level `index_status` 标记 failed；
- command 输出的 import/index 摘要提示 `vector indexing failed`；
- 之后可以通过重新运行 job 或重新触发 workflow 补 index。

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
- Do not create a separate user-facing index module/command for this pipeline.
- `auto_import=False` means discovery returns search result only.
- `SearchStorageImportWorkflow` remains a small adapter, not the full pipeline.
- Runtime commands may set `ignore_import_errors=True` so a storage failure does not discard the search result.
