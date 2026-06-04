# AstrBot Runtime Glue

本文档说明 PaperOS 在 AstrBot 插件环境中的运行边界。

## main.py 职责

- 读取 AstrBot config。
- 初始化 PaperOS config。
- 初始化 search service、storage context 和跨模块 workflow 所需 facade。
- 注册 command。
- 注册 LLM tool。
- 调 presenter 输出用户可读结果，包括 search 结果和 storage 入库摘要。
- 生命周期中关闭 HTTP client 和 storage repository。

## main.py 不应负责

- search pipeline 内部逻辑。
- storage SQL。
- PDF 下载细节。
- RAG 检索细节。

## 当前结构

`main.py` 负责把 AstrBot command/tool 组合到核心模块上。`/paperos search` 当前通过 `PaperDiscoveryWorkflow.discover_and_index(...)` 执行用户级 pipeline：先调用 search service，再在 storage 启用时通过 `SearchStorageImportWorkflow` 完成 narrow storage import，最后用 presenter 输出搜索结果和入库摘要。

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
