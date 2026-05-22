# PaperOS Search：AI Context

本文件是给 ChatGPT / 代码智能体优先阅读的 search 模块黑盒上下文。它说明模块职责、稳定入口、重要数据结构和扩展规则，不追求覆盖源码细节。

## 当前任务边界

`paperos/search/` 只负责“论文搜索与全文候选验证”。

当前 searcher 已实现：

- 从 AstrBot 命令或 LLM tool 接收自然语言 query。
- 用 AstrBot 已配置的大模型把 query 解析成结构化 `SearchPlan`。
- 用 CORE API 搜索候选论文 metadata。
- 对候选做 scoring、dedup、disambiguation。
- 从候选中提取 PDF / landing URL。
- 对全文候选 URL 做轻量验证，判断 `verified_pdf` / `html_fulltext` / `landing_only` / `requires_auth` / `failed` / `invalid`。
- 返回 `PaperSearchResult`，由 presenter 格式化为聊天输出。

当前 searcher 不实现：

- SQLite / LanceDB / 本地数据库入库。
- 自动下载 PDF 到本地文件系统并记录路径。
- PDF 解析、chunk、embedding、RAG。
- 绕过出版社权限、登录、paywall、验证码。

## 稳定入口

外部模块只应调用：

```python
from .paperos.search.service import PaperSearchService

result = await search_service.search(
    raw_query="attention is all you need",
    event=event,
    need_fulltext=True,
)
```

兼容旧代码：

```python
result = await search_service.find_paper(raw_query, event=event)
```

不要在外部直接调用：

- `CoreClient`
- `CoreMetadataProvider`
- `AstrBotLLMQueryAnalyzer`
- `PaperSearchPipeline`
- `FulltextVerifier`

除非正在修改 searcher 内部。

## 典型调用链

```text
main.py command/tool
  ↓
PaperSearchService.search()
  ↓
PaperSearchPipeline.run()
  ↓
AstrBotLLMQueryAnalyzer.analyze()
  ↓
CandidateResolver.resolve()
  ↓
CoreMetadataProvider.search()
  ↓
CoreClient.search_works()
  ↓
score_candidates()
  ↓
PaperDeduplicator.dedup()
  ↓
PaperDisambiguator.select()
  ↓
FulltextResolver.resolve()
  ↓
FulltextProvider.resolve()
  ↓
FulltextVerifier.verify()
  ↓
PaperSearchResult
```

## 与 storage/ingest 的关系

- search 返回候选和 fulltext URL。
- ingest 消费 search 结果，决定是否入库。
- storage 负责 paper/version/object/job 的长期状态。
- downloader 负责把 verified PDF URL 下载成本地 object。
