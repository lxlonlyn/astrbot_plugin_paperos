# AstrBot Runtime Glue

本文档说明 PaperOS 在 AstrBot 插件环境中的运行边界。

## main.py 职责

- 读取 AstrBot config。
- 初始化 PaperOS config。
- 初始化 service facade。
- 注册 command。
- 注册 LLM tool。
- 调 presenter 输出用户可读结果。
- 生命周期中关闭 HTTP client。

## main.py 不应负责

- search pipeline 内部逻辑。
- storage SQL。
- PDF 下载细节。
- RAG 检索细节。

## 推荐结构

当前 `main.py` 只初始化 search service 和 presenter。storage 代码已经存在，但尚未接入插件生命周期；下面是下一步接入 storage 时的推荐结构。

```python
class PaperOSPlugin(Star):
    def __init__(self, context, config):
        super().__init__(context)
        self.cfg = load_config(config)
        self.search_service = PaperSearchService(self.cfg, context)
        self.storage = None

    async def initialize(self):
        storage_cfg = getattr(self.cfg, "storage", None)
        if storage_cfg and storage_cfg.enabled:
            self.storage = await create_storage_context(self.cfg, plugin_name=self.name)

    async def terminate(self):
        if self.storage:
            await self.storage.aclose()
        await self.search_service.aclose()
```

## import 规则

插件内部优先使用相对导入，避免 AstrBot 动态加载时路径错乱。
