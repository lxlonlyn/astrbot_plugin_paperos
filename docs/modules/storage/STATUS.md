# Storage Status

## 当前状态

storage 处于早期可用阶段：SQLite schema、repository、object store、路径初始化和 search/storage workflow 已经有代码实现，并已接入 `/paperos search` 的 AstrBot command 主流程。

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
- 后续文档处理任务排队：目标 job type 为 `storage_parse_pdf`。
- verified PDF 导入 object store。后续 PDF parse/chunk/FTS 应由 storage document processing 推进；embedding/vector index 应由 RAG 推进。
- PDF -> TEI -> normalized document -> chunks / FTS 的职责已归入 storage 文档处理；具体 worker 尚未实现。

## 未完成

- 已新增 storage document processor/GROBID/TEI/chunker 模块骨架；尚未实现 job worker 与 SQL rows 持久化主流程。
- 尚未实现 RAG embedding/vector indexer。
- LLM tool `paperos_search_paper` 当前仍只返回搜索结果，不做隐式入库，避免模型工具调用产生用户未预期的持久化写入。

## 暂不作为第一阶段目标

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
- 不要把 embedding/vector/retrieval 放进 storage。
- 不要把数据库放在插件源码目录。
- 不要在没有 migration 的情况下直接修改 schema。
