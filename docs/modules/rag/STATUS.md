# RAG Status

## 当前状态

尚未作为稳定模块实现。

## 未来依赖

- storage schema 中的 `paper_chunks`。
- storage schema 中的 `paper_chunks_fts`。
- API embedding provider。
- 本地 vector store，例如 LanceDB。

## 第一阶段目标

- local FTS search。
- chunks retrieval。
- 简单 context builder。

## 第二阶段目标

- API query embedding。
- LanceDB vector search。
- FTS + vector hybrid retrieval。
- rerank。
