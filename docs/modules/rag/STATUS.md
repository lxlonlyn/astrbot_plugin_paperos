# RAG Status

## 当前状态

尚未作为稳定模块实现。当前 docs 先固定边界：RAG 是解析、chunk、embedding、index、retrieval 和本地证据分析的归属模块。

## 第一阶段目标

- PDF/text object parser。
- chunker。
- `storage.replace_chunks(...)` 接入。
- local FTS retrieval。
- 简单 context builder。

## 第二阶段目标

- API chunk embedding。
- API query embedding。
- 本地 vector index。
- FTS + vector hybrid retrieval。
- index status 写回 storage。
- paper QA / claim extraction / idea generation workflow。

## 不属于 RAG

- 联网找论文。
- 下载 PDF URL。
- 长期对象归档。
- SQLite schema 迁移实现。
