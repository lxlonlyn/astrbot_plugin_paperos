# PaperOS 模块边界

本文档是 PaperOS 后续实现和重构时的边界约束。任何新功能在落代码前应先检查本文档，避免把联网、持久化、RAG、科研推理混成一团。

## 总原则

PaperOS 只保留少数顶层语义模块：

```text
paperos/
  search/     # 外部资源发现与获取
  storage/    # 本地论文库与对象存储
  rag/        # 只基于本地库的检索问答
  reasoning/  # 基于本地证据的科研推理
```

不要把 `crawler`、`downloader`、`indexer`、`parser` 继续提升为顶层平级模块。它们应该放在对应语义模块内部。

核心依赖方向：

```text
AstrBot handler / facade
    ├── search
    ├── storage
    └── rag

search  -> LLM / web / crawler / downloader / verifier
storage -> SQLite / object store / vector store / jobs
rag     -> storage / embedding provider / LLM
```

禁止出现：

```text
rag -> search
storage -> search
storage -> network
```

## main.py

负责：

- AstrBot `Star` 入口。
- command / command group / tool 注册。
- 从 AstrBot 配置读取 PaperOSConfig。
- 调用稳定 facade 或 service。
- 将 presenter 的文本返回给用户。

不负责：

- 爬网页。
- 下载 PDF。
- 写 SQL。
- 做 embedding。
- 解析 PDF。

AstrBot 插件应保留 `metadata.yaml`、`_conf_schema.json`、`requirements.txt` 等标准文件；依赖必须写入 `requirements.txt`，配置 Schema 由 `_conf_schema.json` 描述。

## search

`search` 是“从网上找资源”的模块。crawler、site resolver、downloader、verifier 都属于 search 的内部实现。

负责：

- 将用户自然语言输入解析为 `SearchPlan`。
- 调用 LLM 生成少量、精确、可执行的 web search query。
- 使用 on-demand web search 找候选页面。
- 只爬取少量候选页面，不做年份/会议全集离线爬取。
- 针对 arXiv、OpenReview、ACL Anthology、CVF、PMLR 等站点做 domain-specific URL 规范化。
- 提取 `citation_*` meta、PDF link、landing page、标题、作者、年份、摘要等。
- 下载候选 PDF 到 searcher 临时目录，并验证魔数、大小、页数。
- 返回 `PaperSearchResult` / `PaperCandidate` / `FulltextLocation`。

不负责：

- SQLite 入库。
- 长期对象路径管理。
- 解析 PDF 正文。
- chunk / embedding / vector index。
- RAG answer generation。

默认策略：

```text
LLM SearchPlan
  -> on-demand web search
  -> targeted crawler
  -> domain resolver
  -> PDF verifier
  -> score / dedup / disambiguate
```

CORE / OpenAlex / Crossref / Semantic Scholar 这类学术 API 不再参与默认主链路。它们只能作为未来的可选 metadata enrichment，不影响搜索与下载体验。

## storage

`storage` 是 PaperOS 的本地事实源。它只接收已经拿到的 metadata、local file 或 chunk，不主动联网。

负责：

- PaperOS 内部 ID。
- SQLite schema / migration。
- papers、identifiers、aliases、versions、objects、fulltext_locations、jobs、chunks、index_status。
- content-addressed object store。
- 本地去重和版本关系。
- vector store 的本地持久化接口。

不负责：

- 联网搜索。
- URL 下载。
- HTML 爬取。
- 调用 embedding provider。
- 生成回答。

特别规则：

- `storage` 不能 import `paperos.search.models`。
- `storage` 使用自己的 `storage.models.PaperRecordDraft` 和 `FulltextLocationRecord`。
- search result -> storage record 的转换应该发生在上层 facade 或 adapter，不放进 repository 内部。

## rag

`rag` 是本地论文库上的问答系统。

负责：

- 基于 storage 的 FTS / vector / hybrid retrieval。
- query embedding。
- chunk rerank 与上下文构造。
- citation-aware answer。
- 读取 storage 中的论文、chunk、向量索引状态。

不负责：

- 在线找论文。
- 下载 PDF。
- 爬网页。
- 修改 searcher 的候选排序。

当 RAG 检索不到内容时，它最多返回“本地库没有相关论文”，不自动调用 search。是否扩充本地库应由用户命令或上层 facade 决定。

## reasoning

`reasoning` 是科研辅助层，只使用本地证据或用户明确提供的内容。

负责：

- idea generation。
- related work 草稿。
- 方法比较。
- claim / experiment / limitation 抽取。

不负责：

- 原始论文搜索。
- 文件生命周期。
- 数据库 schema。

## 下载与入库责任

下载责任归 `search`：

```text
search.acquire/verifier
  -> 访问 URL
  -> 下载临时 PDF
  -> 验证 PDF
  -> 返回 local_path / sha256 / size / page_count
```

长期保存责任归 `storage`：

```text
storage.object_store
  -> 接收已验证 local file
  -> 计算 sha256
  -> 移入 content-addressed object store
  -> 写 objects / versions / fulltext_locations
  -> 创建 parse/chunk/embed job
```

storage 不应该拿 URL 自己下载；search 不应该决定长期 object storage key。
