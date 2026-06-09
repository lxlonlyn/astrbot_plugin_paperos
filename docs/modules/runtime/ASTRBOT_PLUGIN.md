# AstrBot Runtime Glue

本文档说明 PaperOS 在 AstrBot 插件环境中的运行边界。

## main.py 职责

- 注册 command。
- 注册 LLM tool。
- 读取 AstrBot command 的 `event.message_str` 并提取 query。
- 初始化一个 `PaperOSApp` 应用门面。
- 把 `PaperOSCommandResponse` 转成 AstrBot `plain_result` / `chain_result`。
- 生命周期中调用 `PaperOSApp.initialize()` / `PaperOSApp.close()`。

## main.py 不应负责

- search pipeline 内部逻辑。
- storage SQL。
- PDF 下载细节。
- PDF/GROBID/chunker 细节。
- RAG embedding、vector index 或检索细节。
- search/storage/rag service 的依赖组装。
- presenter 文本拼接。
- PDF 发送路径选择。

## 当前结构

`main.py` 是 AstrBot adapter。它只面对一个应用对象：

```text
main.py
  -> PaperOSApp
      -> PaperDiscoveryWorkflow / RagService / StorageDiagnostics
      -> search / storage / rag
```

`PaperOSApp` 位于 `paperos/app.py`，负责持有 search/storage/rag services、presenters、storage context 和 workflow 组装逻辑。它返回 framework-neutral 的 `PaperOSCommandResponse(text, file_path=None, file_name=None)`，不依赖 AstrBot message components。

`/paperos search` 当前通过 `PaperOSApp.search(...)` 执行：调用 `PaperDiscoveryWorkflow.discover_and_index(...)`，在 storage 启用时完成 search result -> storage import、storage-owned PDF document processing；如果 import result 带有 `parser_run_id`，workflow 会调用注入的 `RagIndexService.index_parser_run(...)` 完成 embedding/vector indexing 后处理。`PaperOSApp` 负责 presenter 文本拼接和 PDF 文件路径选择。

`paperos_search_paper` LLM tool 仍只返回搜索结果，不做隐式入库/index，避免模型工具调用产生用户未预期的持久化写入。

`PaperOSApp` 是应用门面，不是核心数据模块。search -> storage -> rag 的实际业务编排仍属于 `paperos.workflows`。

当前命令：

- `/paperos search <query>`
- `/paperos config`
- `/paperos storage status`
- `/paperos storage info <paper_id|doi|arxiv|title>`

```python
class PaperOSPlugin(Star):
    def __init__(self, context, config):
        super().__init__(context)
        self.os = PaperOSApp(
            cfg=load_config(config),
            astrbot_context=context,
            plugin_name=getattr(self, "name", "astrbot_plugin_paperos"),
        )

    async def initialize(self):
        await self.os.initialize()

    async def terminate(self):
        await self.os.close()
```

## import 规则

插件内部优先使用相对导入，避免 AstrBot 动态加载时路径错乱。
