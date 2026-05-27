# Search 模块

Search 模块负责在线发现和获取论文资源。它不是 RAG，也不是 storage。

## 职责

```text
用户自然语言
  -> LLM QueryAnalyzer
  -> SearchPlan
  -> WebSearchEngine
  -> TargetedPaperCrawler
  -> DomainResolver
  -> FulltextVerifier
  -> PaperSearchResult
```

默认不使用 CORE/OpenAlex/Crossref/Semantic Scholar 等学术 API。API 的问题是它们经常只能给 metadata 或 landing/hint URL，无法保证可下载 PDF。PaperOS 的 searcher 更关心“这几篇论文能不能找到并验证全文”。

## 子目录

```text
paperos/search/
  query/          # LLM/fallback QueryAnalyzer
  crawl/          # web search、targeted crawler、site resolver、HTML extraction
  acquire/        # PDF verifier/downloader，负责临时下载和验证
  resolve/        # score、dedup、disambiguation
  models.py       # search-only DTO
  pipeline.py     # orchestration
  service.py      # AstrBot-facing search facade
  presenter.py    # command/tool 输出格式化
```

`crawl` 不提升为顶层模块，因为它只是 searcher 的实现细节。

## On-demand crawler 策略

PaperOS 不做全量爬取，例如“爬取 2026 年某会议所有文章”。每次只根据用户意图生成少量 query，并限制候选数量：

```text
每个 query top-k
总候选页面上限 max_total_results
每篇论文 PDF 候选上限 max_fulltext_candidates
```

## Domain resolver

优先支持：

- arXiv: `/abs/{id}` -> `/pdf/{id}.pdf`
- OpenReview: `/forum?id=xxx` -> `/pdf?id=xxx`
- ACL Anthology: `https://aclanthology.org/{id}/` -> `{id}.pdf`
- PMLR/CVF/项目页/作者主页: 从 HTML meta 和 a[href] 中提取 PDF

遇到 ACM/IEEE 等受限页面时，只记录 landing page 或尝试寻找公开 PDF，不绕过访问控制。

## 验证规则

`FulltextVerifier` 必须：

- 使用 `loc.request_headers`。
- 限制最大文件大小。
- 检查内容不是 HTML landing page。
- 检查文件头 `%PDF-`。
- 使用 `pypdf` 读取页数。
- 只有验证成功才标记 `VERIFIED_PDF`。

## Debug 日志

建议保留以下日志点：

- query analyze 输出的 intent/hypothesis 数量。
- 每个 search query 返回多少网页候选。
- 每个页面抽取出多少 PDF candidate。
- 每个 PDF candidate 的验证状态。
- 去重前后候选数量。
