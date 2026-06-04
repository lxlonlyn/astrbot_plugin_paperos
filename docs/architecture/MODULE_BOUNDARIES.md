# PaperOS module boundaries

本文档是 PaperOS 的最高优先级边界规则。其他 AI 在修改仓库前应先读这里，再按模块读取对应的 `AI_CONTEXT.md`。

## Core modules

PaperOS 的论文数据链路只保留三个核心模块：

- `search`: 联网获取有效 paper。输入可以是单篇论文线索，也可以是带数量限制的 topic。输出应包含论文 metadata、候选/已验证 PDF、来源与匹配依据。
- `storage`: 本地持久化事实源和文档数据处理层。负责保存、更新、查询、返回持久化数据，也负责已归档 PDF 的本地解析、TEI/normalized document、chunks 和 FTS。不联网搜索，不调用 LLM，不调用 embedding provider。
- `rag`: 本地检索、向量索引和回答层。负责从 storage 的 chunks / normalized document 开始，调用外部 embedding provider 获取向量，维护 vector index，并执行 retrieval / answer / analysis workflow。

`reasoning` 不是论文数据链路的核心模块。idea generation、claim 整理、related work 草稿等能力应优先作为 `rag` 的上层应用或 workflow，而不是新的底层数据模块。

`ingest` 也不是顶层模块。搜索结果入库、PDF 归档、解析/索引任务推进应作为 command/facade/workflow 组合 `search -> storage -> rag`。

`workflows` 不是第四个核心模块，而是跨模块 orchestration 层。核心模块不得反向 import workflow。

## Dependency direction

```text
AstrBot command/tool/workflow
  -> search
  -> storage
  -> rag
```

Allowed:

- command/facade 调用 `search` 后，把结果转换为 storage DTO 再写入 `storage`。
- `storage` 可以调用本地 GROBID 服务或本地 parser，把已归档 PDF 转成 TEI、normalized document、chunks 和 FTS。
- `rag` 从 `storage` 读取 chunks / normalized document，调用 embedding provider，并把 vector/index status 写回 `storage`。
- `search` 下载并验证临时 PDF，返回可交给 storage 归档的本地路径。

Forbidden:

- `storage -> search`
- `storage -> external network for paper discovery or PDF download`
- `storage -> external paper search`
- `storage -> LLM/embedding provider`
- `search -> storage`
- `rag -> search`
- `search/storage/rag -> workflows`
- 把 crawler/downloader/verifier/GROBID adapter/chunker/indexer 提升为顶层模块

## Search boundary

Search is online acquisition.

It may:

- call AstrBot LLM provider to turn a user query into a `SearchPlan`;
- when AstrBot session config enables `provider_settings.web_search`, call exactly one configured AstrBot built-in web-search tool in a code-controlled way to collect URL evidence;
- follow concrete sources such as DOI, arXiv, ACM DL, OpenReview, ACL, direct PDF URLs;
- perform small precise-title lookups on known scholarly sites such as arXiv/ACM;
- download temporary PDF files;
- validate that a file is a real PDF;
- return `PaperSearchResult` containing metadata and verified fulltext locations.

It must not:

- write SQLite;
- maintain its own generic web-search backend separate from AstrBot;
- crawl venues/journals in bulk;
- own long-term object paths;
- parse PDF text into chunks;
- compute embeddings;
- answer local library questions.

## Storage boundary

Storage is persistence only.

It may:

- initialize directories and SQLite schema;
- store paper/version/identifier/alias/object/fulltext/job/chunk/index metadata;
- move an already-local verified file into the object store;
- call a local GROBID service or local parser for archived PDFs;
- convert PDF to TEI XML, normalized document, chunks, and FTS;
- persist document processing status and processing artifacts;
- return persisted rows and object paths.

It must not:

- fetch URLs;
- download PDFs;
- call external paper-search/enrichment APIs;
- call LLM providers;
- call embedding providers;
- decide search strategy;
- perform RAG retrieval or answer generation.

## RAG boundary

RAG is local embedding, retrieval, and answer generation.

It may:

- read chunks / normalized document data from storage;
- call external embedding providers for chunks and query embeddings;
- write vector records and index status back through storage APIs;
- perform FTS/vector/hybrid retrieval;
- build answer context and paper-level analysis outputs.

It must not:

- search the internet for new papers;
- download PDFs from URLs;
- call GROBID or parse PDFs into chunks;
- bypass storage when persisting chunks or vectors;
- mutate search candidate ranking.

If local data is missing, RAG should report that the library lacks the paper/data. A command or workflow may then explicitly run `search` and persist the result before invoking RAG again.
