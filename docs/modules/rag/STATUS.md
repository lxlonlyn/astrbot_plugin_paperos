# RAG Status

## 当前状态

已实现 Phase 1 的最小 FTS-only RAG。当前代码包含：

- `paperos/rag/models.py`
- `paperos/rag/retrieval.py`
- `paperos/rag/context/evidence.py`
- `paperos/rag/providers.py`
- `paperos/rag/indexing.py`
- `paperos/rag/service.py`
- `paperos/rag/presenter.py`

`/paperos rag <query>` 会读取 storage 已生成的 `paper_chunks_fts`，返回 evidence chunks。它不生成复杂答案，不调用 searcher，不调用 embedding provider。

已新增 Phase 2 的基础索引服务，但尚未接入命令或 job runner：

- `resolve_embedding_provider(context, provider_id="")`：只解析 AstrBot 已配置的 embedding provider。
- `RagIndexService.index_parser_run(parser_run_id)`：读取 storage chunks，调用 AstrBot embedding provider，通过 storage-owned `LocalVectorIndex` 写 `VectorRecord`，并更新 chunk-level `chunk_embedding_status` 与 paper-level `index_status`。
- `RagIndexService.index_paper(paper_id)`。
- `RagIndexService.index_pending_job(job)`：只处理明确 job payload，不 claim、不 mark done/failed。
- RAG 不实例化 LanceDB，不接收 `vector_index_dir`，不决定 vector index 如何建表或存储。

当前 docs 固定边界：RAG 不拥有 PDF parser、GROBID、chunker 或 PDF -> text。Storage 负责 document processing 和 chunks；RAG 负责 FTS/vector retrieval、embedding/vector index、EvidencePack、answer generation 和 search expansion hints。

这里的“解析”只允许指 provider/result parsing，例如 embedding provider response、retrieval result、rerank result、LLM answer JSON 或 search expansion hints。PDF/GROBID/TEI/chunking 的 document parsing 属于 storage。

## Phase 1: FTS-only RAG

当前已实现基础 FTS-only，不上 embedding/vector。

原因：

- storage 已有 `paper_chunks_fts`。
- 可以马上验证 chunks 是否可用。
- 实现成本低。
- 不依赖 embedding API。

目标：

- `RagService.retrieve_local(query, filters=None)`：已实现。
- `RagService.build_evidence_pack(query, chunks)`：已实现。
- `RagService.retrieve_evidence(query, filters=None)`：已实现。
- `repository.search_chunks_fts(query, paper_id=None, limit=20)`：已实现。
- `repository.get_chunks_by_ids(ids)`：已实现。
- `repository.get_neighbor_chunks(chunk_id, before=1, after=1)`：已实现。
- `EvidenceBuilder`：已实现。
- `/paperos rag <query>` evidence-only output：已实现。
- `AnswerBuilder` / LLM answer：未实现，后续在 retrieval 稳定后再做。

## Phase 2: Embedding + Vector Index

- `RagIndexService`：基础实现已完成。
- load parser_run/paper chunks：已完成。
- resolve AstrBot embedding provider：已完成。
- batch embedding API：已完成。
- write storage-owned vector index：已完成，通过 `LocalVectorIndex.upsert_vectors(...)`。
- update `index_status`：已完成。
- `RagIndexJobRunner`：未实现。
- claim `rag_embed_chunks` job：未实现，后续由 workflow/job runner 负责。
- chunk-level embedding status：已完成，通过 storage repository `upsert_chunk_embedding_status(...)`。
- `RagVectorService` / `VectorRetriever` / hybrid retrieval：未实现。

## Phase 3: Hybrid Retrieval

- FTS retriever。
- vector retriever。
- RRF fusion。
- neighbor expansion。
- optional rerank。
- EvidencePack output。

## Phase 4: Search Expansion Hints

- `RagService.build_search_context(query) -> SearchContextDraft`。
- RAG 返回 hints，不调用 searcher。
- workflow 可把 hints 转成 searcher 的 SearchContext。

## Phase 5: Evidence-Based Analysis

- Paper QA。
- claim extraction。
- related work draft。
- idea expansion。

这些都必须建立在 retrieve -> EvidencePack -> answer 上。

## 不属于 RAG

- 联网找论文。
- 下载 PDF URL。
- 长期对象归档。
- PDF -> TEI / normalized document / chunks。
- FTS 构建。
- SQLite schema 迁移实现。
