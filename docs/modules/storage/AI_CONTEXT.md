# PaperOS Storage：AI Context

本文件是给 ChatGPT / 代码智能体优先阅读的 storage 模块黑盒上下文。

## 当前任务边界

`paperos/storage/` 只负责本地持久化数据的保存、更新、查询和返回。
它同时拥有已归档 PDF 的本地文档处理：PDF -> TEI -> normalized document -> chunks / FTS。

这里的“解析”指 document parsing / structuring：把 PDF、GROBID TEI 或本地 parser output 转成可持久化的 PaperOS 文档结构。它不同于 RAG 对 embedding provider response、检索结果或 LLM JSON 的解析。

Storage 负责：

- paper / version / identifier / alias。
- object metadata 与本地 object store。
- fulltext location 记录。
- job 状态。
- 本地 GROBID 服务或本地 parser adapter。
- TEI XML、normalized document、chunk、FTS 和 document processing 状态。
- vector/index metadata 的持久化接口。
- 本地去重和稳定内部 ID。

Storage 不负责：

- 外部论文搜索。
- 网络下载 PDF。
- 调用 LLM。
- 调用 embedding provider。
- RAG retrieval 或 answer generation。

## 为什么不能用 sha256 当 paper id

`sha256` 是文件对象级字段，只能说明两个文件 bytes 是否相同。它不能表达：

- 同一篇论文的 arXiv v1/v2/v3。
- 同一篇论文的 preprint 与 publisher final。
- 同一篇论文 metadata 更新。
- 多个 provider 返回同一篇论文但 PDF URL 不同。

因此 storage 使用内部稳定 ID：

```text
p_xxx     paper id
pv_xxx    paper version id
obj_xxx   object id
job_xxx   job id
chk_xxx   chunk id
```

外部 ID，例如 DOI、arXiv、CORE、OpenAlex、Semantic Scholar，放入 `paper_identifiers` 表。

## 与 search 的关系

search 返回 `PaperSearchResult`。storage 不再二次联网搜索，只消费上层 facade 转换后的 storage DTO：

```text
search.PaperSearchResult / search.PaperCandidate
  -> paperos.workflows.search_storage converts
  -> storage.PaperRecordDraft
  -> repository.upsert_paper()
  -> object_store.put_file(existing verified local PDF)
  -> repository.register_object()
  -> repository.attach_object_to_current_version()
  -> repository.enqueue_job("storage_parse_pdf")
```

Search 阶段下载并验证的 PDF 只是临时文件。storage 只接收已经存在的本地文件或 bytes，并将其归档为长期 object。

当前设计不建议拆成 `/paperos search` 与 `/paperos add` 两段式流程，因为 searcher 中的候选 metadata 和临时 PDF 是同一次在线获取的结果。正确方式是在 `/paperos search` 这条 workflow 内完成 search -> storage 传递；如果 storage 成功归档 PDF，临时 searcher PDF 可以由 workflow 清理。Storage 自身仍不 import search，也不负责生成聊天返回文案。

## 文档处理边界

Storage 负责本地文档处理，允许调用本地 GROBID 服务或本地 parser：

```text
storage object PDF
  -> local GROBID/parser
  -> TEI XML
  -> normalized document
  -> chunks
  -> repository.replace_chunks(...)
  -> FTS / document processing status
```

这里的 GROBID/local parser 是文档数据后处理，不是联网论文搜索，也不是 LLM/embedding 调用。

## 与 RAG 的关系

RAG 负责 embedding、vector index、retrieval 和回答/分析。它消费 storage 中已经存在的 chunks / normalized document：

```text
storage chunks / normalized document
  -> rag embedding provider
  -> vector index
  -> hybrid retrieval / answer context
  -> storage index status update
```

Storage 可以保存 vector/index metadata，但不调用 embedding provider，也不决定 RAG 排序和回答策略。

## 第一版推荐能力

- 初始化 SQLite schema。
- 自动创建数据目录。
- upsert paper draft。
- 按 identifier / normalized title 查重。
- register fulltext location。
- enqueue / claim / finish job。
- register object。
- paper <-> object link。
- current version 更新。
- PDF -> TEI -> normalized document -> chunks / FTS。
- 入库后排队 `storage_parse_pdf`；同步文档处理完成后 storage importer 排队 `rag_embed_chunks`，由 workflow/job runner 调用 RAG indexing 并标记 job 状态。
- vector/index status 持久化接口。
