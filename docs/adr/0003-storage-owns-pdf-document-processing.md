# ADR 0003: Storage owns PDF document processing

## 状态

Accepted

## 背景

PaperOS 需要把已归档 PDF 转换成可长期保存、可重建索引、可供 RAG 使用的结构化数据。

早期文档把 PDF parser、chunker 放入 `rag`。这会让 RAG 同时承担文档数据生产和检索/回答两类职责，边界变得混乱。GROBID 这类工具的核心作用是把 PDF 等科学文档抽取、解析并重构为结构化 XML/TEI；其产物是长期文档数据，而不是一次性的 RAG 推理结果。

## 决策

Storage 拥有 PDF document processing：

```text
storage object PDF
  -> local GROBID service or local parser
  -> TEI XML
  -> normalized document
  -> chunks
  -> FTS / persisted document state
```

RAG 从 storage 已产出的文档数据开始：

```text
storage chunks / normalized document
  -> embedding provider
  -> vector index
  -> hybrid retrieval
  -> answer / analysis workflow
```

## 边界

Storage 仍然不允许：

- 联网搜索论文；
- 从 URL 下载 PDF；
- 调用 LLM；
- 调用 embedding provider；
- 生成回答；
- 执行 RAG retrieval。

Storage 允许：

- 调用本地 GROBID 服务或本地 PDF parser；
- 把 PDF 转成 TEI XML；
- 把 TEI 转成 normalized document；
- 生成 chunks；
- 写入 chunks、FTS 和 document processing 状态；
- 管理 document processing jobs。

这里的 “本地 GROBID 服务” 指本机或内网部署的文档解析服务，不是外部论文搜索后端。

## 影响

- `paperos/storage` 可以新增 document processor、GROBID adapter、TEI normalizer、chunker。
- `paperos/rag` 不再拥有 PDF parser/chunker；它只消费 storage 中的 chunks / normalized document。
- `rag_index_pdf` 这类命名应调整为 storage 文档处理 job 与 RAG embedding/index job 两段：
  - storage: `storage_parse_pdf`
  - rag: `rag_embed_chunks` / `build_vector_index`
- FTS 可由 storage 构建和维护，因为它是 persisted local document search state。
- Vector index 和 embedding provider 调用归 RAG。
