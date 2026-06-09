# PaperOS architecture overview

PaperOS 是 AstrBot 插件中的论文系统。为了让其他 AI 快速定位上下文，项目按黑盒模块组织，而不是按所有实现细节平铺。

## Core data flow

```text
User / LLM Tool / AstrBot Command
        ↓
search: find paper metadata + verified PDF
        ↓
storage: persist paper/version/object/fulltext metadata + parse/chunk/FTS
        ↓
rag: embed, vector index, retrieve, analyze
```

## Module intent

- `search`: 联网获取论文。它可以处理单篇论文查找，也可以处理有限数量的 topic 搜索。它可复用 AstrBot 内置 web search 作为受控 URL 证据来源，也可做小范围精确标题站点 lookup；最终输出应是可验证的 paper metadata 和 PDF/fulltext 信息。
- `storage`: 本地事实源和文档数据处理层。它保存和返回持久化数据，也负责已归档 PDF 的本地 GROBID/parser 处理、TEI/normalized document、chunks 和 FTS；不做联网论文搜索，不调用 LLM 或 embedding provider。
- `rag`: 本地检索、向量索引和分析层。它从 storage 产出的 chunks / normalized document 开始，调用外部 embedding provider、维护 vector index，并基于本地库回答或生成分析。

复杂分析、idea generation、claim extraction、related work 草稿等能力不再作为独立 `reasoning` 模块维护。它们应作为 `rag` 能力或 workflow/pipeline 步骤出现。

## First stable loop

第一阶段优先完成可恢复的数据闭环：

```text
search candidate
  -> verified local PDF
  -> storage paper upsert
  -> storage object register/link
  -> storage PDF -> TEI -> normalized document -> chunks/FTS
  -> rag embed/vector index/retrieve
  -> storage chunks/index status
```

## Long-term target

```text
PDF / metadata
  -> persistent object
  -> storage document processing
  -> storage chunks / FTS
  -> rag embedding provider
  -> local vector/FTS index metadata
  -> retrieval
  -> paper QA / claim extraction / idea generation
```

## Principles

1. `search` 很强，但只做外部发现、临时下载和 PDF 验证，不拥有本地长期状态。
2. `storage` 是 source of truth；SQLite、对象文件、chunks、index status 都通过 storage 读写。
3. PDF -> TEI -> normalized document -> chunks/FTS 属于 `storage` 的本地文档处理流程。
4. embedding provider 和 vector retrieval 属于 `rag`，不属于 storage。
5. 跨模块复杂操作放在 `paperos.workflows` pipeline 层；不要新增 `runtime`、`reasoning`、`ingest` 之类顶层模块。
6. `sha256` 是对象完整性和文件级去重字段，不是 paper id。
7. 新文档应优先说明模块黑盒入口、职责和禁止事项，再链接具体实现文件。
