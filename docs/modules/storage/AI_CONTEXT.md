# PaperOS Storage：AI Context

本文件是给 ChatGPT / 代码智能体优先阅读的 storage 模块黑盒上下文。

## 当前任务边界

`paperos/storage/` 负责 PaperOS 的本地长期状态：

- paper / version / identifier / alias。
- object metadata 与本地 object store。
- fulltext URL 记录。
- ingest/download/parse/chunk/embed job 状态。
- chunk 与 FTS 表。
- index 状态。

storage 不负责：

- 外部论文搜索。
- 网络下载 PDF。
- PDF 解析。
- embedding 计算。
- RAG answer generation。

## 为什么不能用 sha256 当 paper id

`sha256` 是文件对象级字段，只能说明两个文件 bytes 是否相同。它不能表达：

- 同一篇论文的 arXiv v1/v2/v3。
- 同一篇论文的 preprint 与 publisher final。
- 同一篇论文 metadata 更新。
- 多个 provider 返回同一篇论文但 PDF URL 不同。

因此 storage 使用内部稳定 ID：

```text
p_xxx     paper id，代表一篇论文
pv_xxx    paper version id，代表这篇论文的某个版本
obj_xxx   object id，代表一个本地对象文件
job_xxx   job id，代表一个异步/可恢复任务
chk_xxx   chunk id，代表一个 RAG chunk
```

外部 ID，例如 DOI、arXiv、CORE、OpenAlex、Semantic Scholar，放入 `paper_identifiers` 表。

## 与 search 的关系

search 返回 `PaperSearchResult`。storage 不再二次联网搜索，只消费 search 输出中的：

- `PaperCandidate` metadata。
- DOI / arXiv / CORE / OpenAlex / Semantic Scholar 等 identifier。
- `download_url` / `landing_url`。
- `FulltextLocation`。

本地去重由 storage/ingest 完成，区别于 search-stage dedup。

## 与 ingest 的关系

storage 提供 repository 和 object store。ingest 编排：

```text
PaperSearchResult
  -> LocalPaperDeduplicator / Repository.upsert_candidate
  -> fulltext_locations register
  -> enqueue download_pdf job
  -> downloader writes object
  -> repository marks current version
```

## 第一版推荐能力

第一版 storage 应至少支持：

- 初始化 SQLite schema。
- 自动创建数据目录。
- upsert paper candidate。
- 按 identifier / normalized title 查重。
- register fulltext location。
- enqueue / claim / finish job。
- register object。
- paper <-> object link。
- current version 更新。
