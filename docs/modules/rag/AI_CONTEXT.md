# PaperOS RAG：AI Context

本文件是给 ChatGPT / 代码智能体优先阅读的 RAG 模块黑盒上下文。

## 当前任务边界

`paperos/rag/` 负责 embedding、向量索引、检索和基于本地证据的分析。

RAG 负责：

- 从 storage 读取已持久化的 paper、object、chunk、job 和 index status。
- 调用外部 embedding provider 获取 chunk embedding 和 query embedding。
- 将 embedding/vector 记录和 vector/index status 通过 storage API 写回本地数据库。
- 执行 FTS/vector/hybrid retrieval。
- 构造 LLM answer context。
- 在本地证据基础上做 paper QA、claim extraction、idea generation、related work 草稿等上层分析。

RAG 不负责：

- 联网搜索论文。
- 从 URL 下载 PDF。
- 调用 GROBID 或解析 PDF 为 chunks。
- 维护 storage 文档处理 schema。
- 维护 SQLite schema 的底层细节。
- 绕过 storage 直接散落写数据库或索引文件。
- 修改 search 的候选排序或 PDF 验证策略。

## 推荐子能力

RAG 可以按能力拆分内部文件，但不要把它们提升为顶层模块：

- embedding indexer：调用 embedding provider，写入 vector/index 状态。
- retriever：执行 FTS/vector/hybrid retrieval。
- context builder：把检索结果组织为 LLM 可用上下文。
- analysis workflows：idea、claim、method、limitation、related work 等。

## 推荐索引流程

```text
storage chunks / normalized document
  ↓
rag embedding indexer calls embedding provider
  ↓
storage records vector metadata / index status
```

## 推荐检索流程

```text
query
  ↓
query embedding via API provider
  ↓
FTS top_k + vector top_k
  ↓
fusion / rerank
  ↓
neighbor expansion
  ↓
context builder
  ↓
answer / analysis workflow
```

## 设计原则

SQLite 中的 paper/chunk/object/index metadata 是 source of truth。向量索引可以是 SQLite 表、LanceDB 或其他本地可重建索引，但写入和状态更新应通过 storage 边界完成。

PDF -> TEI -> normalized document -> chunks / FTS 属于 storage 的本地文档处理职责，不属于 RAG。
