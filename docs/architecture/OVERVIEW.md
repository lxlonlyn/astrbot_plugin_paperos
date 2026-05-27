# PaperOS architecture overview

PaperOS 是 AstrBot 插件中的论文系统。为了让其他 AI 快速定位上下文，项目按黑盒模块组织，而不是按所有实现细节平铺。

## Core data flow

```text
User / LLM Tool / AstrBot Command
        ↓
search: find paper metadata + verified PDF
        ↓
storage: persist paper/version/object/fulltext metadata
        ↓
rag: parse, chunk, embed, index, retrieve, analyze
```

## Module intent

- `search`: 联网获取论文。它可以处理单篇论文查找，也可以处理有限数量的 topic 搜索。最终输出应是可验证的 paper metadata 和 PDF/fulltext 信息。
- `storage`: 本地事实源。它只保存和返回持久化数据，不做联网查询，不调用 LLM 或 embedding provider，不做 PDF 解析。
- `rag`: 本地论文数据处理和检索分析。它负责解析文章、生成 chunks、调用外部 embedding provider、写入本地索引数据，并基于本地库回答或生成分析。

`reasoning` 可以作为未来的应用层术语存在，但不应成为搜索、存储、文章数据处理链路中的第四个必读模块。idea generation、claim extraction、related work 草稿等能力优先放在 RAG workflow 文档下。

## First stable loop

第一阶段优先完成可恢复的数据闭环：

```text
search candidate
  -> verified local PDF
  -> storage paper upsert
  -> storage object register/link
  -> rag parse/chunk/embed/index
  -> storage chunks/index status
```

## Long-term target

```text
PDF / metadata
  -> persistent object
  -> parse
  -> chunk
  -> embedding provider
  -> local vector/FTS index metadata
  -> retrieval
  -> paper QA / claim extraction / idea generation
```

## Principles

1. `search` 很强，但只做外部发现、临时下载和 PDF 验证，不拥有本地长期状态。
2. `storage` 是 source of truth；SQLite、对象文件、chunks、index status 都通过 storage 读写。
3. embedding provider 属于 `rag` 的索引流程，不属于 storage。
4. `sha256` 是对象完整性和文件级去重字段，不是 paper id。
5. 新文档应优先说明模块黑盒入口、职责和禁止事项，再链接具体实现文件。
