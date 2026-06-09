# AstrBot Runtime Glue

本文档说明 PaperOS 在 AstrBot 插件环境中的运行边界。

## main.py 职责

- 读取 AstrBot config。
- 初始化 PaperOS config。
- 初始化 search service、storage context 和跨模块 workflow 所需 facade。
- 在 `/paperos search` command 路径中把 storage repository/vector index 和 AstrBot context 注入 `RagIndexService`。
- 通过 `_build_discovery_workflow()`、`_build_rag_service()`、`_build_storage_diagnostics()` 这类薄 helper 隔离依赖组装细节。
- 注册 command。
- 注册 LLM tool。
- 调 presenter 输出用户可读结果，包括 search 结果、storage 入库摘要和 RAG indexing 摘要。
- 生命周期中关闭 HTTP client 和 storage repository。

## main.py 不应负责

- search pipeline 内部逻辑。
- storage SQL。
- PDF 下载细节。
- PDF/GROBID/chunker 细节。
- RAG embedding、vector index 或检索细节。

## 当前结构

`main.py` 负责把 AstrBot command/tool 组合到核心模块上。`/paperos search` 当前通过 `PaperDiscoveryWorkflow.discover_and_index(...)` 执行用户级 pipeline：先调用 search service，再在 storage 启用时通过 `SearchStorageImportWorkflow` 完成 narrow storage import 和 storage-owned PDF document processing；如果 import result 带有 `parser_run_id`，workflow 会调用注入的 `RagIndexService.index_parser_run(...)` 完成 embedding/vector indexing 后处理。presenter 输出搜索结果、入库摘要和 indexing 摘要。

`paperos_search_paper` LLM tool 仍只返回搜索结果，不做隐式入库/index，避免模型工具调用产生用户未预期的持久化写入。

`main.py` 可以保留少量 builder helper，但这些 helper 只做 AstrBot runtime 的依赖组装；search -> storage -> rag 的实际编排仍属于 `paperos.workflows`。

当前命令：

- `/paperos search <query>`
- `/paperos config`
- `/paperos storage status`
- `/paperos storage info <paper_id|doi|arxiv|title>`

```python
class PaperOSPlugin(Star):
    def __init__(self, context, config):
        super().__init__(context)
        self.cfg = load_config(config)
        self.search_service = PaperSearchService(self.cfg, context)
        self.storage_presenter = StoragePresenter()
        self.storage = None

    async def initialize(self):
        if self.cfg.storage.enabled:
            self.storage = await create_storage_context(self.cfg, plugin_name=self.name)

    async def terminate(self):
        if self.storage:
            await self.storage.aclose()
        await self.search_service.aclose()
```

## import 规则

插件内部优先使用相对导入，避免 AstrBot 动态加载时路径错乱。
