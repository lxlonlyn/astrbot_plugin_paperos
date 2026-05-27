# Search 快速决策表

## 我想搜索论文

```python
await PaperSearchService.search(raw_query, event=event, need_fulltext=True)
```

不要直接调 `CoreClient`。

## 我想只要 metadata，不验证全文

```python
await PaperSearchService.search(raw_query, event=event, need_fulltext=False)
```

## 我想把搜索结果显示给用户

```python
text = PaperSearchPresenter(cfg).format_search_result(result)
```

不要在 `main.py` 或其他模块手写格式化。

## 我想新增一个搜索 API

先确认它是否仍符合 search 边界：只负责联网获取有效 paper，不负责入库、解析、embedding 或回答。

当前默认主链路不使用通用 web search 后端，也不使用 CORE/OpenAlex/Semantic Scholar 主链路。新增来源应优先作为 `TargetedPaperCrawler` / `DomainResolver` 的站点规则，或作为未来可选 metadata enrichment，不要扩大 search 的顶层职责。

## 我想新增一个 PDF/OA 来源

把站点 URL 归一化和 PDF candidate 生成放在 `search/crawl/` 内部，例如 `DomainResolver` 或 targeted crawler 的 HTML 提取逻辑。

如果来源是 arXiv/ACM 这类可按准确标题查询的站点，可以在 `TargetedPaperCrawler` 里增加小结果集 title lookup。不要把它扩展成会议列表批量爬虫或通用网页搜索。

## 我想下载 PDF

这属于 search 的在线获取职责。下载后必须由 `FulltextVerifier` 严格验证，返回 searcher 临时本地路径。临时 PDF 必须放在 AstrBot 插件数据目录 `get_astrbot_data_path()/plugin_data/astrbot_plugin_paperos/searcher/fulltext/`；长期归档交给 storage object store。

## 我想存数据库

不要放进 search pipeline。应在上层 command/facade 中把 `PaperCandidate` 转成 `storage.PaperRecordDraft` 后调用 storage repository。
