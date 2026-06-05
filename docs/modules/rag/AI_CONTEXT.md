# PaperOS RAG：AI Context

本文件是给 ChatGPT / 代码智能体优先阅读的 RAG 模块黑盒上下文。

## 当前任务边界

`paperos/rag/` 负责本地 evidence retrieval、embedding/vector index、context construction 和基于证据的回答/分析。

Storage 已拥有 PDF document processing：PDF -> TEI -> normalized document -> chunks / FTS。RAG 从 storage 已生成的 `paper_chunks`、FTS、normalized document 和 citation metadata 开始工作。

RAG 中的“解析”只指 provider/result parsing：解析 embedding provider response、vector-search result、rerank result、LLM answer JSON 或 search expansion hints。RAG 不解析 PDF、GROBID TEI，不生成 storage chunks。

## 当前已实现

Phase 1 最小实现已经可用：

- `RagService.retrieve_local(query, filters=None)`：从 storage FTS 读取 chunk 命中。
- `RagService.build_evidence_pack(query, chunks)`：补齐 paper metadata、section/page 和 neighbor chunks。
- `RagService.retrieve_evidence(query, filters=None)`：组合 retrieval 和 evidence builder。
- `/paperos rag <query>`：返回 evidence chunks，不生成复杂答案。

Phase 2 基础 indexing service 已经可用，但尚未接命令或 job runner：

- `resolve_embedding_provider(context, provider_id="")`：使用 AstrBot context 的 `get_all_embedding_providers()`。
- 如果配置了 `rag.embedding_provider_id`，按 provider id/name 匹配。
- 如果未配置且只有一个 embedding provider，自动使用。
- 如果未配置且有多个 embedding provider，抛出明确配置错误。
- 调用 provider 的 `get_dim()`；embedding 优先使用 AstrBot `get_embeddings_batch(texts, batch_size=...)`，没有该方法时才按 `rag.embedding_batch_size` 分批调用 `get_embeddings(list[str])`。
- 不自造 Qwen/OpenAI provider。
- `RagIndexService.index_parser_run(parser_run_id)` / `index_paper(paper_id)` / `index_pending_job(job)`。
- `RagIndexService` 接收 storage-owned `LocalVectorIndex`，不实例化 LanceDB，不接收 `vector_index_dir`。
- indexing service 组织 storage `VectorRecord`，不包含 chunk 正文 text。
- indexing service 通过 `LocalVectorIndex.upsert_vectors(...)` 写向量，通过 repository 写 `chunk_embedding_status` 和 `index_status`。
- RAG 正文、metadata、citation 仍必须从 storage 读取；vector index 不是 source of truth。

当前 `/paperos rag <query>` 不调用 embedding provider，不做 vector retrieval，不调用 searcher，不调用 LLM。

RAG 负责：

- 从 storage 读取 `paper_chunks`、paper metadata、normalized document、index status。
- FTS-only retrieval：先消费 storage 的 `paper_chunks_fts`，验证 chunks 是否可用。
- 调用外部 embedding provider 获取 chunk embedding 和 query embedding。
- 解析 embedding provider 返回值，并把向量和模型 metadata 转成 RAG index records。
- 写入 vector index，并通过 storage 更新 index status。
- 执行 FTS/vector/hybrid retrieval。
- 做 neighbor expansion、fusion、optional rerank。
- 构造 EvidencePack，保留 paper、section、page、chunk、citation 信息。
- 调 LLM 只基于 EvidencePack 生成回答。
- 为 workflow 提供 search expansion hints，但不直接调用 searcher。

RAG 不负责：

- PDF parser。
- GROBID。
- chunker。
- PDF -> text / TEI / normalized document。
- 联网搜索论文。
- 从 URL 下载 PDF。
- storage schema 底层迁移。
- 绕过 storage 直接散落写数据库或索引文件。
- 修改 search 的候选排序或 PDF 验证策略。

## 推荐目录结构

这是未来实现结构，不代表当前已存在代码：

```text
paperos/rag/
  __init__.py
  models.py
  service.py
  config.py

  embeddings/
    __init__.py
    interfaces.py
    astrbot_provider.py
    batcher.py

  indexes/
    __init__.py
    interfaces.py
    lancedb_store.py
    metadata.py

  retrieval/
    __init__.py
    fts.py
    vector.py
    fusion.py
    rerank.py
    neighbors.py

  context/
    __init__.py
    evidence.py
    builder.py
    citations.py

  generation/
    __init__.py
    prompts.py
    answer.py

  jobs.py
```

## Phases

Phase 1: FTS-only RAG.

- `RagService.retrieve_local(query, filters=None)`。
- 调用 storage repository 的 `search_chunks_fts(...)`。
- 返回 `RetrievedChunk[]`。
- `EvidenceBuilder` 根据 chunk ids 拉取 paper title、section、page、text。
- `/paperos rag <query>` 返回 evidence chunks。
- 不依赖 embedding API，不写 vector index。
- `AnswerBuilder` / LLM answer 留到后续 evidence-based generation。

Phase 2: embedding + vector index.

- `RagIndexService` 已实现基础索引能力。
- RAG indexing 已迁移到 storage-owned vector interface。
- job claim / mark done / mark failed 仍由未来 workflow/job runner 负责。
- load parser_run/paper chunks。
- filter missing/stale chunk embedding status。
- resolve AstrBot embedding provider。
- batch embedding API：优先使用 AstrBot provider 自带的 `get_embeddings_batch`，fallback 到 batched `get_embeddings(list[str])`。
- build storage `VectorRecord[]` without chunk text。
- write through `LocalVectorIndex.upsert_vectors(...)`。
- update index status。
- update chunk-level `chunk_embedding_status`。
- `RagVectorService` / `VectorRetriever` / hybrid retrieval 尚未实现；不要把它们塞进 `RagIndexService`。

Phase 3: hybrid retrieval.

- `FTSRetriever`。
- `VectorRetriever`。
- `HybridRetriever`。
- RRF fusion: `score = 1 / (60 + rank_fts) + 1 / (60 + rank_vector)`。
- neighbor expansion。
- optional rerank。

Phase 4: search expansion hints.

- `RagService.build_search_context(query) -> SearchContextDraft`。
- 返回 related papers、concepts、aliases、known identifiers、positive/negative query terms、suggested search queries、local context summary。
- RAG 只返回 hints；workflow 再转换为 searcher 的 SearchContext 并显式调用 search。

Phase 5: paper QA / claim / related work.

- `PaperQAService`。
- `ClaimExtractionService`。
- `RelatedWorkDraftService`。
- `IdeaExpansionService`。
- 全部建立在 retrieve -> EvidencePack -> answer 上，不让 LLM 凭记忆写。

## Storage Methods Needed

RAG Phase 1 需要 storage repository 提供：

- `search_chunks_fts(query, paper_id=None, limit=20)`
- `get_chunks_by_ids(ids)`
- `get_neighbor_chunks(chunk_id, before=1, after=1)`
- `get_paper_citation_metadata(paper_id)`

这些方法只读 storage 已持久化数据，不触发 search，不调用 embedding provider。

当前 SQLite repository 已暴露这些 Phase 1 只读方法。

RAG Phase 2 indexing 需要 storage repository 提供：

- `get_chunks_for_parser_run(parser_run_id)`
- `get_chunks_for_paper(paper_id)`
- `list_missing_or_stale_chunk_embeddings(...)`
- `upsert_chunk_embedding_status(...)`
- `update_index_status(paper_id=..., index_name=..., status=..., profile=..., message=...)`

这些方法只读/写 storage 持久化状态，不调用 embedding provider；provider 调用仍在 RAG。
