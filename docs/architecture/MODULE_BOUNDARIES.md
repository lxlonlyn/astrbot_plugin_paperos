# PaperOS module boundaries

本文档是 PaperOS 的最高优先级边界规则。其他 AI 在修改仓库前应先读这里，再按模块读取对应的 `AI_CONTEXT.md`。

## Core modules

PaperOS 的论文数据链路只保留三个核心模块：

- `search`: 联网获取有效 paper。输入可以是单篇论文线索，也可以是带数量限制的 topic。输出应包含论文 metadata、候选/已验证 PDF、来源与匹配依据。
- `storage`: 本地持久化事实源。只负责保存、更新、查询和返回持久化数据。不联网，不调用 LLM，不调用 embedding provider，不解析 PDF。
- `rag`: 本地论文数据处理、索引、检索和回答。负责把 storage 中的 PDF/文本解析成 chunks，调用外部 embedding provider 获取向量，并把 chunk/vector/index 状态写回 storage。

`reasoning` 不是论文数据链路的核心模块。idea generation、claim 整理、related work 草稿等能力应优先作为 `rag` 的上层应用或 workflow，而不是新的底层数据模块。

`ingest` 也不是顶层模块。搜索结果入库、PDF 归档、解析/索引任务推进应作为 command/facade/workflow 组合 `search -> storage -> rag`。

## Dependency direction

```text
AstrBot command/tool/workflow
  -> search
  -> storage
  -> rag
```

Allowed:

- command/facade 调用 `search` 后，把结果转换为 storage DTO 再写入 `storage`。
- `rag` 从 `storage` 读取 papers/objects/chunks/jobs，调用 embedding provider，并把 chunks/vector/index status 写回 `storage`。
- `search` 下载并验证临时 PDF，返回可交给 storage 归档的本地路径。

Forbidden:

- `storage -> search`
- `storage -> network`
- `storage -> LLM/embedding provider`
- `search -> storage`
- `rag -> search`
- 把 crawler/downloader/verifier/parser/indexer 提升为顶层模块

## Search boundary

Search is online acquisition.

It may:

- call AstrBot LLM provider to turn a user query into a `SearchPlan`;
- follow concrete sources such as DOI, arXiv, OpenReview, ACL, direct PDF URLs;
- download temporary PDF files;
- validate that a file is a real PDF;
- return `PaperSearchResult` containing metadata and verified fulltext locations.

It must not:

- write SQLite;
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
- return persisted rows and object paths.

It must not:

- fetch URLs;
- download PDFs;
- call LLM providers;
- call embedding providers;
- parse PDF text;
- decide search strategy;
- perform RAG retrieval or answer generation.

## RAG boundary

RAG is local data processing and retrieval.

It may:

- read PDF/text objects from storage;
- parse papers into text/chunks;
- call external embedding providers for chunks and query embeddings;
- write chunks, vector records, and index status back through storage APIs;
- perform FTS/vector/hybrid retrieval;
- build answer context and paper-level analysis outputs.

It must not:

- search the internet for new papers;
- download PDFs from URLs;
- bypass storage when persisting chunks or vectors;
- mutate search candidate ranking.

If local data is missing, RAG should report that the library lacks the paper/data. A command or workflow may then explicitly run `search` and persist the result before invoking RAG again.
