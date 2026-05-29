# Ingest Status

## 当前状态

不作为独立顶层模块稳定实现。入库能力应作为 command/facade/workflow 组合 `search -> storage -> rag`。

## 如需实现，应属于 workflow

- `/paperos search <query>` 同一次 workflow 内的 search result -> storage upsert。
- ambiguous result 的用户确认策略。
- verified PDF 归档到 storage object store。
- 触发 RAG parse/chunk/embed/index。
- `/paperos status <paper_id>` 或最近任务状态查询。

## 暂不实现

- 复杂并发 worker。
- 大规模批处理。
- 自动概念图谱。
- 高级 PDF parser。
