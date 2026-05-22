# PaperOS RAG：AI Context

RAG 是未来用于本地论文问答与上下文构造的模块。

## 职责

- 从 storage 读取 chunks。
- 使用 SQLite FTS、LanceDB vector index 或 hybrid retrieval。
- 调用 API embedding provider 生成 query embedding。
- 合并 FTS/vector 结果。
- rerank。
- 邻接 chunk 扩展。
- 构造 LLM answer context。

## 不负责

- 搜索外部论文。
- 下载 PDF。
- 解析 PDF。
- 修改底层 schema。

## 推荐检索流程

```text
query
  ↓
query embedding via API provider
  ↓
FTS top_k + Vector top_k
  ↓
RRF fusion
  ↓
per-paper cap
  ↓
optional rerank
  ↓
neighbor expansion
  ↓
context builder
```

## 设计原则

SQLite 是 chunk source of truth。LanceDB/vector index 是可重建索引，不能成为唯一数据源。
