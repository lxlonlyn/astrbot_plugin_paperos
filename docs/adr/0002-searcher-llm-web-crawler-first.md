# ADR 0002: Searcher 采用 LLM + Targeted Crawler 优先，不再默认使用学术 API

## 状态

Accepted。

## 背景

PaperOS 的目标是个人科研 RAG。用户通常不是要构建完整学术数据库，而是希望通过一句自然语言描述找到少量真实可读的论文，并尽快下载、验证、入库。

原设计依赖 CORE API 作为主搜索/下载入口。但实践中出现以下问题：

- API 可以返回 metadata，但 PDF 下载链接不稳定。
- arXiv 可能返回 `/abs/` 页面而不是 PDF。
- ACM、IEEE、出版商页面常受限，API 无法保证全文可下载。
- 同一篇论文可能出现 arXiv、publisher、author homepage、project page 等多个 URL，API 的去重不一定符合用户认知。
- 用户常给模糊记忆或主题，例如“attention 的奠基文章”，LLM 更适合将其转换成少量搜索假设。

## 决策

PaperOS searcher 默认采用：

```text
LLM SearchPlan
  -> TargetedPaperCrawler
  -> DomainResolver
  -> PDF Verifier
  -> score / dedup / disambiguate
```

CORE / OpenAlex / Crossref / Semantic Scholar 不再参与默认 search/download 主链路。它们未来可作为可选、异步、低优先级 metadata enrichment。

## 非目标

- 不做全量 venue/year 离线爬取。
- 不绕过付费墙或访问控制。
- 不把 crawler 提升为顶层模块。
- 不让 storage 联网。
- 不让 rag 自动调用 search。

## 影响

优点：

- 更符合个人 RAG 的“少量、按需、可读全文”目标。
- 降低 CORE 下载失败对用户体验的影响。
- 站点规则可以集中在 `search/crawl` 内部，不污染 storage/rag。
- LLM 负责模糊意图与语义去重，verifier 负责事实校验。

代价：

- 模糊标题/主题请求依赖 LLM 是否能提出明确来源。
- 少数站点 HTML 改版时需要更新 resolver。
- citation count、DOI 补全等 metadata 需要后续 enrichment 异步补齐。

## 实现约束

- `search/crawl` 内部可以联网。
- `storage` 不能 import `search`。
- `rag` 不能 import `search`。
- 搜索结果中只有 `FulltextStatus.VERIFIED_PDF` 才能被视为可入库 PDF。
- `request_headers` 必须传给 verifier/downloader，以支持未来 provider-owned download endpoint。
