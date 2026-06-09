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

- `storage_parse_pdf`
- `storage_reparse_pdf`
- `rag_embed_chunks`
- `build_fts`
- `build_vector_index`

`storage_parse_pdf`、FTS 和 chunk 相关 job 属于 storage document processing。`rag_embed_chunks` / `build_vector_index` / embedding 相关 worker 属于 `paperos/rag/`。

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

`paper_chunks` 是 embedding 的 source of truth。chunk 的生成策略属于 storage document processing；embedding 调用属于 RAG。

扩展字段：

- `parser_run_id`
- `chunk_type`
- `section_path`
- `content_hash`
- `embedding_text`
- `source_block_ids_json`
- `prev_chunk_id`
- `next_chunk_id`

`text` 保存原始 chunk 正文；`embedding_text` 保存未来传给 embedding provider 的格式化文本。storage 生成 `embedding_text`，但不调用 embedding provider。

## chunk_embedding_status

记录 chunk-level embedding/vector 写入状态，用来避免重复调用 embedding provider，并在 chunk 内容变化时识别 stale 状态。

唯一键：

```text
chunk_id + content_hash + embedding_provider_id + embedding_model + embedding_dim + vector_profile
```

关键字段：

- `chunk_id`
- `paper_id`
- `parser_run_id`
- `content_hash`
- `embedding_provider_id`
- `embedding_model`
- `embedding_dim`
- `vector_backend`
- `vector_profile`
- `vector_table`
- `status`
- `error_message`
- `created_at`, `updated_at`

真实正文、section、page、citation 仍回 SQLite `paper_chunks` 和相关表读取；vector index record 不保存 chunk 正文。

## parser_runs

记录每次 PDF 文档处理。

关键字段：

- `paper_id`
- `version_id`
- `object_id`
- `parser_name`
- `parser_version`
- `status`
- `raw_output_object_id`
- `normalized_object_id`
- `message`
- `created_at`, `updated_at`

raw TEI XML 和 normalized document JSON 作为 object store 中的长期对象，由 `raw_output_object_id` 和 `normalized_object_id` 关联。

## document_sections / document_blocks

`document_sections` 保存章节树；`document_blocks` 保存线性文档块。

典型 block type：

- `title`
- `abstract`
- `paragraph`
- `list_item`
- `formula`
- `figure_caption`
- `table_caption`
- `footnote`
- `reference_context`

## extracted_assets

记录图、表、公式等解析资产。`figure_caption`、`table_caption`、`formula` 可作为 `document_blocks` 保存，并由 `extracted_assets.linked_block_id` 关联。资产文件本身仍通过 `objects` 表和 object store 保存。

默认正文 chunk 不混入 figure/table caption 或 formula；后续 asset-aware retrieval 可以按查询意图单独打开这些证据。

## paper_references

记录 bibliography。`resolved_paper_id` 仅保存已解析出的本地关联；如果需要 Crossref/OpenAlex/Semantic Scholar 等外部解析，应由 search/enrichment workflow 处理，不属于 storage。

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

index status 只描述 paper-level 持久化汇总状态。FTS/document processing 状态可由 storage 更新；embedding 调用由 RAG 执行，但 chunk-level 结果状态必须通过 storage repository 写入 `chunk_embedding_status`。
