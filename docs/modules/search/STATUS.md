# Search Status

## 已实现

- LLM query analyzer。
- fallback query analyzer：可从原始输入识别 DOI、arXiv ID、URL，并为标题/主题生成基础假设。
- targeted crawler：只跟进 SearchPlan 中已有的明确来源，不做通用网页搜索。
- 已知站点 URL 归一化：arXiv、OpenReview、ACL Anthology、直接 PDF URL。
- 候选 scoring。
- search-stage dedup。
- disambiguation。
- fulltext location resolve。
- fulltext PDF 下载、落盘与严格验证。
- presenter 格式化。
- AstrBot command `/paperos search` 与 LLM tool `paperos_search_paper`。

## 未实现

- 多 provider 聚合。
- 通用网页搜索后端。
- CORE/OpenAlex/Semantic Scholar 等学术 API 主链路。
- `/paperos search` 自动写入本地 storage。
- PDF 解析、chunk、embedding。
- RAG retrieval。

## 重要边界

searcher 负责在线发现、临时下载和验证 PDF，但它不拥有长期本地状态。

当前主链路是：

```text
User query
  -> AstrBotLLMQueryAnalyzer
  -> SearchPlan
  -> TargetedPaperCrawler
  -> DomainResolver
  -> FulltextVerifier
  -> PaperSearchResult
```

`FulltextStatus.VERIFIED_PDF` 表示候选 URL 已下载到 `plugin_data/astrbot_plugin_paperos/searcher/fulltext/`，并通过 PDF 文件头和 `pypdf` 页数校验。长期入库、对象归档、解析任务排队应由 storage/library 层完成。

Legacy CORE provider 代码仍保留在 `paperos.search.providers`、`core_client.py` 等文件中，但当前 `PaperSearchService` 不会把它们接入默认搜索流程。
