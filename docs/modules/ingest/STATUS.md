# Ingest Status

## 当前状态

尚未作为独立模块稳定实现。

## 第一阶段应实现

- `/paperos ingest <query>`。
- search result -> storage upsert。
- ambiguous result 的用户确认策略。
- verified_pdf URL 的下载任务提交。
- `/paperos status <paper_id>` 或最近任务状态查询。

## 暂不实现

- 复杂并发 worker。
- 大规模批处理。
- 自动概念图谱。
- 高级 PDF parser。
