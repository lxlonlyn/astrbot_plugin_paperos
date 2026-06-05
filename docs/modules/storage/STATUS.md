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
- chunk-level embedding 状态表：`chunk_embedding_status`。
- storage-owned vector index 接口：`LocalVectorIndex` / `LanceDBVectorIndex`。
- search DTO 到 storage DTO 的转换：`paperos.workflows.search_storage.paper_candidate_to_record()`。
- search result 到 storage 的传递入口：`SearchStorageImportWorkflow.import_search_result()`。
- verified PDF 归档为 storage object，并可选清理 searcher 临时 PDF。
- 后续文档处理任务排队：目标 job type 为 `storage_parse_pdf`。
- verified PDF 导入 object store 后，会立即尝试 storage document processing：PDF -> GROBID TEI -> normalized document -> chunks / FTS。
- 同步文档处理成功后，`storage_parse_pdf` job 会标记 done，并排队 `rag_embed_chunks`。失败时入库仍保留，`storage_parse_pdf` job 标记 failed，并在导入摘要中返回错误提示。

## 未完成

- 尚未实现独立后台 job worker；当前 `/paperos search` 入库后会同步执行一次 storage document processing。
- 尚未迁移 RAG embedding indexer 到 storage-owned vector/index-status 接口。
- LLM tool `paperos_search_paper` 当前仍只返回搜索结果，不做隐式入库，避免模型工具调用产生用户未预期的持久化写入。

## 暂不作为第一阶段目标

- 公式/表格/图片抽取。
- concept graph。
- 多人同步。
- 外置数据库。

## 风险点

- 不要用 `sha256`、DOI、arXiv ID 作为 `paper_id`。
- 不要让 search pipeline 直接写 SQLite。
- 不要让 provider 下载 PDF。
- 不要让 storage 调用 embedding provider。
- 不要把 embedding provider 调用、retrieval 策略或答案生成放进 storage；storage 只拥有本地 vector index 的物理读写接口和状态表。
- 不要把数据库放在插件源码目录。
- 不要在没有 migration 的情况下直接修改 schema。
