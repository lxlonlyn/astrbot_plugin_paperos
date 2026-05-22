# PaperOS 文档索引

> 面向未来对话、协作者、代码智能体的黑盒文档。
>
> 阅读原则：优先读 `docs/` 中的模块文档理解边界和公开入口；只有文档不能回答具体实现问题时，才回退到源码。

## 文档结构

```text
docs/
  API_INDEX.md                         # 全局入口，本文件
  architecture/                        # 跨模块架构与边界
    OVERVIEW.md
    MODULE_BOUNDARIES.md
  modules/                             # 每个业务模块的黑盒文档
    search/
      AI_CONTEXT.md
      API.md
      PROVIDER_CONTRACT.md
      STATUS.md
      QUICK_DECISION_TABLE.md
    storage/
      AI_CONTEXT.md
      API.md
      SCHEMA.md
      CONFIGURATION.md
      STATUS.md
      QUICK_DECISION_TABLE.md
    ingest/
      AI_CONTEXT.md
      STATUS.md
    rag/
      AI_CONTEXT.md
      STATUS.md
    reasoning/
      AI_CONTEXT.md
      STATUS.md
    runtime/
      ASTRBOT_PLUGIN.md
      CONFIGURATION.md
  templates/
    MODULE_DOC_TEMPLATE.md
  adr/
    0001-docs-module-layout.md
  api/                                 # 兼容旧路径；不要再新增正文文档
    README.md
```

## 推荐阅读顺序

### 只想理解整体边界

1. [`architecture/OVERVIEW.md`](architecture/OVERVIEW.md)
2. [`architecture/MODULE_BOUNDARIES.md`](architecture/MODULE_BOUNDARIES.md)
3. 当前正在修改的模块目录，例如 [`modules/search/`](modules/search/) 或 [`modules/storage/`](modules/storage/)

### 只想使用 searcher

1. [`modules/search/AI_CONTEXT.md`](modules/search/AI_CONTEXT.md)
2. [`modules/search/API.md`](modules/search/API.md)
3. [`modules/search/QUICK_DECISION_TABLE.md`](modules/search/QUICK_DECISION_TABLE.md)

### 只想实现本地存储

1. [`modules/storage/AI_CONTEXT.md`](modules/storage/AI_CONTEXT.md)
2. [`modules/storage/SCHEMA.md`](modules/storage/SCHEMA.md)
3. [`modules/storage/API.md`](modules/storage/API.md)
4. [`modules/storage/CONFIGURATION.md`](modules/storage/CONFIGURATION.md)

### 只想规划后续模块

- Ingestion：[`modules/ingest/AI_CONTEXT.md`](modules/ingest/AI_CONTEXT.md)
- RAG：[`modules/rag/AI_CONTEXT.md`](modules/rag/AI_CONTEXT.md)
- Reasoning：[`modules/reasoning/AI_CONTEXT.md`](modules/reasoning/AI_CONTEXT.md)
- AstrBot runtime/config：[`modules/runtime/ASTRBOT_PLUGIN.md`](modules/runtime/ASTRBOT_PLUGIN.md)

## 当前稳定调用入口

外部模块，包括 AstrBot handler、未来 ingestion、RAG、reasoning，优先只调用模块 facade，不直接调用内部 pipeline/provider/repository 细节。

```python
# search
result = await PaperSearchService.search(raw_query, event=event, need_fulltext=True)

# storage, planned stable facade
storage = await create_storage_context(cfg, plugin_name=plugin_name)
repo = storage.repository
objects = storage.object_store
```

## 模块总边界

```text
main.py
  AstrBot 入口。只处理命令、tool 注册、用户消息解析、权限、结果展示。

paperos/search/
  外部论文搜索、候选去重、消歧、全文 URL resolve 与轻量验证。
  不负责数据库入库、PDF 下载落盘、PDF 解析、chunk、embedding、RAG。

paperos/storage/
  本地长期身份管理、SQLite schema、对象存储、任务状态、chunk/FTS/index 状态。
  不负责联网搜索、下载、PDF 解析、embedding 计算。

paperos/ingest/
  未来模块。编排 search -> local dedup -> download -> register object -> parse -> chunk -> index jobs。
  不直接实现 search provider，不直接实现底层 SQLite SQL。

paperos/rag/
  未来模块。负责 local retrieval、hybrid retrieval、rerank、context building。
  不负责入库和 PDF 下载。

paperos/reasoning/
  未来模块。负责长任务推理、论文理解、实验/claim 组织。
  不拥有底层论文身份和文件对象。
```

## 维护规则

- 新模块必须在 `docs/modules/<module>/` 下建立独立文档目录。
- 不再向 `docs/api/` 增加新的正文文档；`docs/api/` 只保留兼容旧路径的 README 或跳转说明。
- 每个模块至少包含 `AI_CONTEXT.md` 和 `STATUS.md`。
- 已经稳定对外暴露的模块应补充 `API.md` 和 `QUICK_DECISION_TABLE.md`。
- 涉及 schema、配置、provider contract 的内容应单独拆文件，不要塞进 AI_CONTEXT。
