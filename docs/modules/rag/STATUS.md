# RAG Status

## 当前状态

尚未作为稳定模块实现。当前 docs 先固定边界：RAG 是 embedding、vector index、retrieval 和本地证据分析的归属模块。PDF 解析、TEI normalizing、chunking 和 FTS 属于 storage 文档处理。

## 第一阶段目标

- API chunk embedding。
- API query embedding。
- vector index status 写回 storage。
- local FTS retrieval 消费 storage FTS/chunks。
- 简单 context builder。

## 第二阶段目标

- 本地 vector index。
- FTS + vector hybrid retrieval。
- paper QA / claim extraction / idea generation workflow。

## 不属于 RAG

- 联网找论文。
- 下载 PDF URL。
- 长期对象归档。
- PDF -> TEI / normalized document / chunks。
- FTS 构建。
- SQLite schema 迁移实现。
