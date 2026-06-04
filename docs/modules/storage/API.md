# Storage API

本文档描述 storage 模块对外 facade。具体类名可以随实现调整，但外部应只依赖这些概念，不直接散落 SQL。

## create_storage_context

推荐稳定入口：

```python
storage = await create_storage_context(cfg, plugin_name=plugin_name)
```

返回 `PaperOSStorageContext`，包含：

```python
storage.repository
storage.object_store
storage.paths
```

使用规则：

- `main.py` 或插件生命周期中初始化一次。
- service 之间传递 context 或 repository，不重复解析路径。
- 插件关闭时调用 `await storage.aclose()`。

## Repository

Repository 封装 SQLite 操作。

### upsert_paper

```python
paper_id = await repo.upsert_paper(
    draft,
    source_query=raw_query,
    decision="search_selected",
)
```

职责：

- 接收 `paperos.storage.models.PaperRecordDraft`。
- 规范化 metadata。
- 按 identifier 查重。
- 必要时按 title/year 做本地查重。
- 创建或更新 `papers`。
- 写入 `paper_identifiers`。
- 写入 `paper_aliases`。
- 创建 `paper_versions` 并设置 current version。
- 写入 `fulltext_locations`。
- 写入 `paper_ingest_events`。

不负责：

- 下载 PDF。
- 调用 LLM 或 embedding provider。

### enqueue_job

Repository 保存和领取 job 状态。PDF document processing worker 属于 storage；embedding/vector worker 属于 RAG。

```python
job_id = await repo.enqueue_job(
    job_type="storage_parse_pdf",
    dedupe_key=f"storage_parse_pdf:{object_id}",
    paper_id=paper_id,
    object_id=object_id,
    payload={"source_query": raw_query},
)
```

要求：

- `job_type + dedupe_key` 应唯一，避免重复任务。
- 支持 pending/running/done/failed。
- 支持 stale lock 恢复。
- storage document processing job 可以调用本地 GROBID/parser。
- 不在 storage 内部调用 LLM 或 embedding provider。

### register_object

```python
object_id = await repo.register_object(stored_object)
```

对象由 `ObjectStore` 写入后，再由 repository 记录 metadata。

### attach_object_to_current_version

```python
await repo.attach_object_to_current_version(
    paper_id=paper_id,
    object_id=object_id,
    role="pdf",
)
```

该方法会把 object 挂到 paper 当前 version，并写入 `paper_object_links`。

### attach_object_to_fulltext_location

```python
await repo.attach_object_to_fulltext_location(
    paper_id=paper_id,
    url=verified_pdf_url,
    object_id=object_id,
)
```

该方法把已归档 object 反向关联到对应 `fulltext_locations` 行。这样 diagnostics 可以判断 verified PDF 是否已经 linked 到长期 object。

## ObjectStore

ObjectStore 管理本地文件系统中的大对象。

推荐接口：

```python
stored = await object_store.put_file(
    src_path,
    kind="pdf",
    suffix=".pdf",
)
```

职责：

- 写入 tmp。
- 计算 sha256。
- atomic rename。
- 生成 storage key。
- 返回 size/mime/sha256/storage_key。

不负责：

- 写 paper/version 关系。
- 判断该 PDF 属于哪篇论文。

## SearchStorageImportWorkflow

`paperos.workflows.search_storage.SearchStorageImportWorkflow` 是 search 与 storage 的边界适配层。它可以把 `PaperCandidate` / `PaperSearchResult` 转成 `PaperRecordDraft`，再完成：

- `repository.upsert_paper()`；
- verified PDF 写入 `object_store.put_file()`；
- `repository.register_object()`；
- `repository.attach_object_to_current_version()`；
- `repository.attach_object_to_fulltext_location()`；
- 可选地 `repository.enqueue_job("storage_parse_pdf", ...)`，实际消费方属于 storage document processing workflow；
- 可选地在长期 object 归档成功后清理 searcher 临时 PDF。

返回 `SearchStorageImportSummary` / `SearchStorageImportResult`，包含 `paper_id`、`object_id`、`job_id`、是否归档 PDF、是否仅 metadata 入库、临时 PDF 是否已清理等信息。

`paperos.library.PaperLibraryFacade` 仅保留为兼容 re-export。新代码不要继续从顶层 `paperos.library` 引入。

## RAG Read APIs Needed

RAG Phase 1 需要 repository 增加只读查询方法：

```python
await repo.search_chunks_fts(query, paper_id=None, limit=20)
await repo.get_chunks_by_ids(ids)
await repo.get_neighbor_chunks(chunk_id, before=1, after=1)
await repo.get_paper_citation_metadata(paper_id)
```

这些方法只读 storage 已生成的 chunks / FTS / citation metadata，不调用 search，不调用 embedding provider。
