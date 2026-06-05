# PaperOS API Index

## Search

- `paperos.search.service.PaperSearchService.search(raw_query, event=None, need_fulltext=True, context=None)`
  - 在线查找论文候选并尽力下载、验证 PDF。
  - 不写数据库。
  - 不构建 embedding。
  - QueryAnalyzer 可在 AstrBot 会话启用 `provider_settings.web_search` 时受控调用 AstrBot 内置 web-search 工具补充 URL 证据。

- `paperos.search.models.PaperSearchResult`
  - `status`: `selected` / `ambiguous` / `not_found` / `disabled` / `error`
  - `candidates`: 所有候选
  - `selected`: 自动选中的候选；主题搜索可能多篇

## Storage

- `paperos.storage.interfaces.LocalPaperRepository`
  - 本地论文库协议。
  - 不联网。
  - 使用 `paperos.storage.models.PaperRecordDraft`。

- `paperos.storage.interfaces.ObjectStore`
  - 接收 bytes 或本地 file。
  - 返回 `StoredObject`。

- `paperos.workflows.search_storage.SearchStorageImportWorkflow.import_search_result(result, source_query=None)`
  - search/storage/document-processing 边界 workflow。
  - upsert paper metadata。
  - 将 verified PDF 归档到 object store。
  - 注册 object/version/fulltext-location link。
  - 入队并立即尝试执行 storage 文档处理 job `storage_parse_pdf`；GROBID/parser/chunker 属于 storage。
  - 成功后写入 parser run、TEI/normalized object、chunks/FTS，并排队 `rag_embed_chunks`；失败时保留入库结果并返回错误提示。
  - 已接入 `/paperos search` 的 AstrBot command workflow。

## Workflows

- `paperos.workflows.paper_discovery.PaperDiscoveryWorkflow.discover_and_index(query, need_fulltext=True, auto_import=True, search_context=None)`
  - 用户级 discovery pipeline。
  - 第一阶段同步执行 search 和 storage import。
  - 可选透传 searcher 的 `SearchContext`，但 workflow/searcher 不反向调用 RAG 或 storage 生成它。
  - 后续 storage document processing / RAG embedding 通过 `paper_jobs` 表表达。
  - 返回 `DiscoveryPipelineResult`，包含 search result、import summary、`storage_parse_job_ids`、`rag_job_ids` 和可选 `import_error`。

## AstrBot Commands

- `/paperos search <query>`
  - 调用 `PaperDiscoveryWorkflow.discover_and_index(...)`。
  - storage 启用时自动导入同一次搜索结果，归档 verified PDF，并入队后续文档处理。
  - 发送文件时优先使用 storage object 路径。

- `/paperos storage status`
  - 返回 storage 目录、schema、对象库、统计和 job 状态。

- `/paperos storage info <paper_id|doi|arxiv|title>`
  - 查询本地论文、identifier、object、verified PDF、chunk、index status 和最近 jobs。

## RAG

RAG 从本地 storage 读取 paper/chunk/normalized document/index 数据，不调用 search。Phase 1 先做 FTS-only retrieval 和 EvidencePack；Phase 2 再做 `rag_embed_chunks`、vector index；之后做 hybrid retrieval 和基于证据的回答/分析。PDF -> TEI -> chunks / FTS 属于 storage。RAG 只解析 embedding provider / retrieval / rerank / LLM answer 等运行期结果，不解析 PDF/GROBID 文档结构。若本地证据不足，RAG 返回 search expansion hints，由 workflow 显式调用 search。

See:

- `docs/modules/rag/ARCHITECTURE.md`
- `docs/modules/rag/INDEXING.md`
- `docs/modules/rag/RETRIEVAL.md`
- `docs/modules/rag/SEARCH_CONTEXT.md`
