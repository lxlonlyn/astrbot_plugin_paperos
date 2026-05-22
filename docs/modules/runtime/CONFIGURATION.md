# Runtime Configuration

PaperOS 配置应分模块组织，避免所有配置堆在一个平面。

推荐顶层结构：

```text
general
query_analyzer
core_api
search_policy
storage
ingest
rag
reasoning
```

## 原则

- 已实现的模块配置才暴露到 `_conf_schema.json`。
- future backend 可以先写入文档，不一定暴露到用户配置面板。
- storage 默认本地 SQLite。
- embedding provider 默认走 API，不要求本地 GPU。
