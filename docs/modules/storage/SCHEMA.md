# Storage Schema

SQLite 是 PaperOS 的 source of truth。大文件存文件系统，SQLite 只保存对象 metadata 和逻辑关系。

## schema_migrations

记录 schema 版本。

```sql
schema_migrations(version, name, applied_at)
```

必须存在，避免后续只能删库重来。

## papers

表示“一篇论文”的长期身份。

关键字段：

- `id`: `p_xxx`
- `canonical_title`
- `title_norm`
- `year`
- `venue`
- `current_version_id`
- `created_at`, `updated_at`

不存 PDF 路径。PDF 属于 object/version。

## paper_identifiers

外部标识。

```text
scheme: doi / arxiv / core / openalex / semantic_scholar / url
value: normalized value
paper_id: internal paper id
```

唯一约束：`(scheme, value)`。

## paper_aliases

标题别名、翻译标题、用户别名、规范化查询名。

用途：

- 本地 fuzzy title search。
- 用户用不完整标题查询。
- 中文/英文别名映射。

## paper_versions

表示同一篇论文的某个版本。

关键字段：

- `id`: `pv_xxx`
- `paper_id`
- `version_label`: `arxiv:v1` / `arxiv:v2` / `publisher` / `core:<id>` 等
- `source`
- `source_url`
- `published_at`
- `discovered_at`
- `object_id`
- `is_current`
- `metadata_json`

同一篇论文只应有一个 current version。

## objects

本地文件对象。

关键字段：

- `id`: `obj_xxx`
- `kind`: `pdf` / `markdown` / `parsed_json` / `image` / `table`
- `sha256`
- `size_bytes`
- `mime_type`
- `storage_key`
- `created_at`
- `deleted_at`

`sha256` 可用于文件级去重，但不是 paper id。

## paper_object_links

paper 与 object 的多对多关系。

用途：

- 同一个 PDF 被多个来源关联时避免重复存储。
- 一个 paper 同时关联 pdf、markdown、parsed_json、figures。

## fulltext_locations

searcher/provider 找到并验证过的全文位置。

关键字段：

- `paper_id`
- `version_id`
- `object_id`
- `url`
- `final_url`
- `source`
- `kind`: pdf/html/landing
- `status`: candidate/verified_pdf/html_fulltext/landing_only/requires_auth/failed/invalid
- `filename`
- `sha256`
- `size_bytes`
- `content_type`
- `page_count`
- `confidence`
- `reason`
- `first_seen_at`, `last_seen_at`

注意：search 阶段的 `verified_pdf` 表示已经下载并验证过临时 PDF；它不等价于 storage 的长期 PDF object。只有经过 `ObjectStore.put_file()` 和 `register_object()` 后，才成为长期对象。
`object_id` 用于标记该 fulltext location 已关联到长期对象。

## paper_jobs

任务队列。

推荐 job type：

- `rag_index_pdf`
- `rag_reindex_paper`
- `build_fts`
- `build_vector_index`

这些 job 只表示持久化队列状态；具体 parser/chunker/embedding/indexer worker 属于 `paperos/rag/`。

推荐状态：

- `pending`
- `running`
- `done`
- `failed`

关键字段：

- `dedupe_key`
- `attempts`
- `max_attempts`
- `locked_by`
- `locked_at`
- `heartbeat_at`
- `timeout_seconds`
- `payload_json`
- `error_message`

## paper_chunks / paper_chunks_fts

`paper_chunks` 保存 chunk metadata 与正文。

`paper_chunks_fts` 是 SQLite FTS5 虚表，用于本地关键词检索。

`paper_chunks` 是 embedding 的 source of truth。chunk 的生成策略和 embedding 调用属于 RAG。

## index_status

记录可重建索引状态。

示例：

```text
paper_id
index_type: fts / vector / embedding
status: pending / ready / stale / failed
version
updated_at
```

index status 只描述持久化状态，不表示 storage 负责构建索引。
