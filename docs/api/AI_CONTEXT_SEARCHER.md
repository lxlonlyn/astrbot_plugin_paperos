# PaperOS Searcher：给未来对话/智能体的压缩上下文

本文件是给 ChatGPT / 代码智能体优先阅读的“黑盒上下文”。  
它不追求覆盖所有实现细节，只说明模块职责、稳定入口、重要数据结构和扩展规则。

## 当前任务边界

PaperOS 是 AstrBot 插件中的长期论文系统。`paperos/search/` 只负责“论文搜索与全文候选验证”，不是整个 PaperOS。

当前 searcher 已实现：

- 从 AstrBot 命令或 LLM tool 接收自然语言 query。
- 用 AstrBot 已配置的大模型把 query 解析成结构化 `SearchPlan`。
- 用 CORE API 搜索候选论文 metadata。
- 对候选做 scoring、dedup、disambiguation。
- 从候选中提取 PDF/landing URL。
- 对全文候选 URL 做轻量验证，判断 verified_pdf / html_fulltext / landing_only / requires_auth / failed / invalid。
- 返回 `PaperSearchResult`，由 `PaperSearchPresenter` 格式化为聊天输出。

当前 searcher 未实现：

- SQLite / LanceDB / 本地数据库入库。
- 自动下载 PDF 到本地文件系统并记录路径。
- PDF 解析、chunk、embedding、RAG。
- 多 provider 聚合。当前只有 CORE provider；接口已经为未来扩展准备好。
- 绕过出版社权限、登录、paywall、验证码。

## 最重要的公共入口

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

除非你正在修改 searcher 内部。

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
CoreFulltextProvider.resolve()
    ↓
FulltextVerifier.verify()
    ↓
PaperSearchResult
    ↓
PaperSearchPresenter.format_search_result()
```

## 核心数据结构

### SearchPlan

LLM QueryAnalyzer 的结构化输出。它表示“应该怎么查”，不是最终事实。

关键字段：

- `raw_query`: 原始用户输入。
- `language`: zh/en/unknown 等。
- `intent`: find_specific / find_multiple / topic_discovery / expand_related / download_known。
- `hypotheses`: 多个 `PaperHypothesis`。每个 hypothesis 是一个可验证线索。
- `topic_keywords`: 话题查询关键词。
- `translated_query`: 中文或模糊 query 的英文/规范化表达。
- `max_candidates`: metadata provider 最多返回多少候选。
- `final_limit`: 话题/多论文查询最终选择多少篇。
- `need_fulltext`: 是否解析全文候选 URL。
- `allow_topic_expansion`: 是否允许扩展话题搜索。

### PaperHypothesis

表示 LLM 猜测的一个检索线索。

常见 `kind`：

- doi
- arxiv
- url
- title
- fuzzy_title
- topic
- author_venue_year

注意：LLM 不应编造 DOI。若不确定，应该使用 title/fuzzy_title/topic hypothesis。

### PaperCandidate

Provider 返回的真实候选论文 metadata。

关键字段：

- `title`, `authors`, `year`, `venue`, `publisher`, `abstract`
- `doi`, `arxiv_id`, `core_id`, `openalex_id`, `semantic_scholar_id`
- `citation_count`
- `download_url`, `landing_url`
- `fulltext_locations`
- `source`
- `raw`
- `score`, `score_reason`

### FulltextLocation

一个全文候选位置，可能是 PDF、HTML、landing page。

关键字段：

- `url`
- `source`
- `kind`: pdf/html/landing
- `status`: candidate / verified_pdf / html_fulltext / landing_only / requires_auth / no_open_access / invalid / failed
- `confidence`
- `reason`

### PaperSearchResult

搜索模块最终返回。

关键字段：

- `status`: disabled / not_found / selected / ambiguous / error
- `message`
- `plan`
- `candidates`
- `selected`

## 外部模块应该如何使用

### 只搜索候选，不要求全文

```python
result = await search_service.search(raw_query, event=event, need_fulltext=False)
```

### 搜索并验证全文候选 URL

```python
result = await search_service.search(raw_query, event=event, need_fulltext=True)
```

### 判断是否找到了明确论文

```python
if result.selected:
    paper = result.selected[0]
else:
    # ambiguous 或 not_found，需要人工确认或二次检索
```

### 判断是否有已验证 PDF

```python
from paperos.search.models import FulltextStatus

verified = [
    loc for loc in paper.fulltext_locations
    if loc.status == FulltextStatus.VERIFIED_PDF
]
```

## 重要设计原则

1. `main.py` 不写业务逻辑。只做 AstrBot glue code。
2. `PaperSearchService` 是外部唯一稳定入口。
3. `PaperSearchPipeline` 只做流程编排，不处理聊天格式。
4. `QueryAnalyzer` 使用 LLM 理解 query，但 API/provider 才负责验证事实。
5. provider 层不能直接下载入库，只返回 metadata 或 URL candidate。
6. downloader/storage/RAG 是后续模块，不应混进 searcher。
7. 所有插件内部 import 使用相对导入，避免 AstrBot 动态加载时找不到包。
8. 日志使用 `from astrbot.api import logger`。
