# RAG Status

## 当前状态

尚未作为稳定模块实现。当前代码只有 `paperos/rag/README.md` 和 `__init__.py`。

当前 docs 固定边界：RAG 不拥有 PDF parser、GROBID、chunker 或 PDF -> text。Storage 负责 document processing 和 chunks；RAG 负责 FTS/vector retrieval、embedding/vector index、EvidencePack、answer generation 和 search expansion hints。

## Phase 1: FTS-only RAG

先实现 FTS-only，不上 embedding/vector。

原因：

- storage 已有 `paper_chunks_fts`。
- 可以马上验证 chunks 是否可用。
- 实现成本低。
- 不依赖 embedding API。

目标：

- `RagService.retrieve_local(query, filters=None)`。
- `repository.search_chunks_fts(query, paper_id=None, limit=20)`。
- `EvidenceBuilder`。
- `AnswerBuilder`。
- local evidence-only answer。

## Phase 2: Embedding + Vector Index

- `RagIndexJobRunner`。
- claim `rag_embed_chunks` job。
- load unembedded chunks。
- batch embedding API。
- write vector index。
- update `index_status`。

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
