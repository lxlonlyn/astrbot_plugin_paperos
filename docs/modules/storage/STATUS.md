# Storage Status

## 当前状态

storage 处于早期可用阶段：SQLite schema、repository、object store、路径初始化和 search/storage workflow 已经有代码实现，但还没有接入 `main.py` 的 AstrBot command 主流程。

## 已实现

- 配置读取。
- 数据目录初始化。
- SQLite schema + migrations。
- Repository facade：`SQLitePaperRepository`。
- ObjectStore facade：`LocalFileObjectStore`。
- 内部 ID 生成。
- candidate upsert。
- local dedup。
- fulltext location register。
- job enqueue/claim/finish。
- object register/link。
- chunk 写入与 FTS5 持久化表写入。
- search DTO 到 storage DTO 的转换：`paperos.workflows.search_storage.paper_candidate_to_record()`。
- search result 到 storage 的传递入口：`SearchStorageImportWorkflow.import_search_result()`。
- verified PDF 归档为 storage object，并可选清理 searcher 临时 PDF。
- RAG 后续任务排队：`rag_index_pdf`。
- verified PDF 导入 object store。后续 parse/chunk/embed/index 应由 RAG workflow 推进。

## 未接入或未完成

- `main.py` 尚未调用 `create_storage_context()`。
- `/paperos search` 当前只返回/发送 PDF，不自动调用 `SearchStorageImportWorkflow.import_search_result()`。
- 尚未实现 RAG parser/chunker/indexer；storage 只提供可供其写入的数据表和 repository 方法。

## 暂不作为第一阶段目标

- PDF 版面解析。
- 公式/表格/图片抽取。
- LanceDB 实装。
- concept graph。
- 多人同步。
- 外置数据库。

## 风险点

- 不要用 `sha256`、DOI、arXiv ID 作为 `paper_id`。
- 不要让 search pipeline 直接写 SQLite。
- 不要让 provider 下载 PDF。
- 不要让 storage 调用 embedding provider。
- 不要把 PDF parser/chunker/indexer 放进 storage。
- 不要把数据库放在插件源码目录。
- 不要在没有 migration 的情况下直接修改 schema。
