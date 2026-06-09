# Search Status

## 已实现

- LLM query analyzer。
- 当 AstrBot 当前会话启用 `provider_settings.web_search` 时，QueryAnalyzer 可直接调用 AstrBot 内置网页搜索工具和已配置 API key；搜索 query 由 PaperOS 控制，最多 5 次，不再交给 `tool_loop_agent(...)` 自由循环。
- fallback query analyzer：可从原始输入识别 DOI、arXiv ID、URL，并为标题/主题生成基础假设。
- targeted crawler：跟进 SearchPlan 中已有的明确来源，并可对具体英文标题做小范围 arXiv/ACM 站点 lookup；不做通用网页搜索或会议批量爬取。
- 已知站点 URL 归一化：arXiv、ACM DL、OpenReview、ACL Anthology、直接 PDF URL。
- 精确标题站点 lookup：arXiv API 与 ACM DL 站内检索，小结果集，面向具体文章名而非大范围爬取。
- LLM identifier 反校验：当 LLM 同时给出标题和 DOI/arXiv/URL 时，抓取到的标题必须与计划标题相符，否则该具体来源会被视为错误 identifier。
- 候选 scoring。
- search-stage dedup。
- disambiguation。
- fulltext location resolve。
- fulltext PDF 下载、落盘与严格验证。
- presenter 格式化。
- AstrBot command `/paperos search` 与 LLM tool `paperos_search_paper`。
- `/paperos search` 在 storage 启用时会把同一次搜索结果交给 `PaperDiscoveryWorkflow`：先经 `SearchStorageImportWorkflow` 入库，归档 verified PDF 到 object store，同步尝试 storage document processing；若生成 `parser_run_id`，继续触发 RAG embedding/vector indexing 后处理，并改用 storage object 路径发送文件。

## 未实现

- 多 provider 聚合。
- PaperOS 自己维护的通用网页搜索后端。
- CORE/OpenAlex/Semantic Scholar 等学术 API 主链路。
- 独立后台 storage document processing worker：PDF -> TEI -> normalized document -> chunks / FTS。
- 独立后台 RAG embedding/vector indexing worker。
- RAG retrieval。

## 重要边界

searcher 负责在线发现、临时下载和验证 PDF，但它不拥有长期本地状态。
storage 入库发生在 AstrBot command/workflow 层，不发生在 `PaperSearchPipeline` 内部。

当前主链路是：

```text
User query
  -> AstrBotLLMQueryAnalyzer
  -> SearchPlan
  -> TargetedPaperCrawler
  -> DomainResolver
  -> FulltextVerifier
  -> PaperSearchResult
  -> PaperDiscoveryWorkflow
  -> SearchStorageImportWorkflow
  -> storage document processing
  -> RagIndexService
```

`FulltextStatus.VERIFIED_PDF` 表示候选 URL 已下载到 AstrBot 插件数据目录
`get_astrbot_data_path()/plugin_data/astrbot_plugin_paperos/searcher/fulltext/`，
并通过 PDF 文件头、大小限制、SHA-256 落盘去重和 `pypdf` 页数校验。长期入库、对象归档、document processing 任务排队由 command/workflow 层调用 storage 完成。

Legacy CORE provider 代码仍保留在 `paperos.search.providers`、`core_client.py` 等文件中，但当前 `PaperSearchService` 不会把它们接入默认搜索流程。
