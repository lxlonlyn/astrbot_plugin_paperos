# PaperOS Searcher API Reference

本文件记录 `paperos/search/` 当前应被外部或内部模块依赖的黑盒 API。  
优先根据本文件使用接口；只有遇到实现细节问题时才看源码。

## 1. AstrBot 入口层

### `main.py::PaperOSPlugin`

职责：AstrBot 插件入口。  
应做：命令注册、LLM tool 注册、提取用户原始 query、调用 `PaperSearchService`、调用 `PaperSearchPresenter`。  
不应做：搜索逻辑、API 请求、候选排序、PDF 验证、数据库操作。

#### `search_paper(event: AstrMessageEvent)`

AstrBot 命令：

```text
/paperos search attention is all you need
/paperos search 注意力机制的奠基文章
/paperos search https://doi.org/...
```

黑盒行为：

1. 从 `event.message_str` 手动截取 `/paperos search` 后面的完整 query。
2. 调用 `PaperSearchService.search(raw_query=query_text, event=event, need_fulltext=True)`。
3. 用 `PaperSearchPresenter.format_search_result()` 格式化输出。

注意：

- 不使用 `GreedyStr`，避免注解和参数解析问题。
- 不应把 query `.lower()`，否则会损失标题、URL、DOI 信息。

#### `paperos_search_paper_tool(event, query: str) -> str`

AstrBot LLM tool。  
用于 agent 在对话中主动搜索论文。

黑盒行为：

1. 调用 `PaperSearchService.search(query, event=event, need_fulltext=True)`。
2. 返回 compact 格式的搜索结果字符串。

---

## 2. 搜索服务门面

### `paperos.search.service.PaperSearchService`

外部稳定入口。RAG、reasoning、ingestion、命令 handler 都应该调用它。

#### 构造

```python
search_service = PaperSearchService(
    cfg=PaperOSConfig,
    astrbot_context=context,
)
```

职责：

- 构造 `CoreClient`
- 构造 `AstrBotLLMQueryAnalyzer`
- 构造 metadata providers
- 构造 fulltext providers
- 构造 resolver/dedup/disambiguator/verifier
- 构造 `PaperSearchPipeline`

不负责：

- 聊天格式化
- 数据库存储
- PDF 落盘
- RAG 解析

#### `async search(raw_query: str, *, event=None, need_fulltext=True) -> PaperSearchResult`

最重要的公共 API。

输入：

- `raw_query`: 用户自然语言 query，可以是标题、错误标题、URL、DOI、话题。
- `event`: AstrBot 事件对象。可为 `None`。传入后 QueryAnalyzer 可以使用当前会话模型。
- `need_fulltext`: 是否解析并验证全文候选 URL。

输出：

- `PaperSearchResult`

状态：

- `disabled`: CORE API 关闭。
- `not_found`: 没有 metadata 候选。
- `selected`: 有明确选中的论文。
- `ambiguous`: 有候选，但不满足自动接受条件。
- `error`: 预留状态，当前主要通过 not_found/warning 表示失败。

推荐用法：

```python
result = await search_service.search(
    raw_query="Attention Is All You Need",
    event=event,
    need_fulltext=True,
)
```

#### `async find_paper(raw_query: str, *, event=None) -> PaperSearchResult`

兼容旧代码的 wrapper。等价于：

```python
await search(raw_query, event=event, need_fulltext=True)
```

#### `async aclose() -> None`

释放底层 HTTP client。插件 terminate 时必须调用。

---

## 3. Pipeline

### `paperos.search.pipeline.PaperSearchPipeline`

内部流程编排器。外部一般不直接调用。

#### `async run(raw_query: str, *, event=None, need_fulltext=True) -> PaperSearchResult`

黑盒流程：

1. 检查 `cfg.core_api.enabled`。
2. `query_analyzer.analyze(raw_query, event=event)` 生成 `SearchPlan`。
3. 根据 `need_fulltext` 更新 `plan.need_fulltext`。
4. `_resolve_score_dedup(plan)` 获取候选。
5. 如果无候选且配置允许，调用 `query_analyzer.repair(...)` 修复一次 SearchPlan。
6. 调用 `disambiguator.select(plan, candidates)`。
7. 对 selected 或前 `plan.final_limit` 个候选执行 fulltext resolve/verify。
8. 返回 `PaperSearchResult`。

内部辅助：

#### `_resolve_score_dedup(plan: SearchPlan) -> list[PaperCandidate]`

执行：

```text
CandidateResolver.resolve()
→ score_candidates()
→ PaperDeduplicator.dedup()
→ score_candidates()
```

---

## 4. 数据模型

所有核心模型在：

```python
paperos.search.models
```

### `SearchIntent`

```python
FIND_SPECIFIC
FIND_MULTIPLE
TOPIC_DISCOVERY
EXPAND_RELATED
DOWNLOAD_KNOWN
```

### `HypothesisKind`

```python
DOI
ARXIV
URL
TITLE
FUZZY_TITLE
TOPIC
AUTHOR_VENUE_YEAR
```

### `FulltextStatus`

```python
CANDIDATE
VERIFIED_PDF
HTML_FULLTEXT
LANDING_ONLY
REQUIRES_AUTH
NO_OPEN_ACCESS
INVALID
FAILED
```

### `PaperHypothesis`

LLM 对用户 query 的一个结构化检索假设。

字段：

```python
kind: HypothesisKind
confidence: float
title: str | None
translated_title: str | None
doi: str | None
arxiv_id: str | None
url: str | None
authors: list[str]
year: int | None
venue: str | None
search_queries: list[str]
note: str | None
```

### `SearchPlan`

QueryAnalyzer 的最终输出，供 provider 使用。

字段：

```python
raw_query: str
language: str
intent: SearchIntent
hypotheses: list[PaperHypothesis]
topic_keywords: list[str]
translated_query: str | None
max_candidates: int
final_limit: int
need_fulltext: bool
allow_topic_expansion: bool
raw_llm_output: dict[str, Any]
```

### `PaperCandidate`

metadata provider 返回的候选论文。

字段：

```python
title: str
authors: list[str]
year: int | None
venue: str | None
publisher: str | None
abstract: str | None
doi: str | None
arxiv_id: str | None
core_id: str | None
openalex_id: str | None
semantic_scholar_id: str | None
citation_count: int | None
download_url: str | None
landing_url: str | None
fulltext_locations: list[FulltextLocation]
source: str
raw: dict[str, Any]
score: float
score_reason: str
```

### `FulltextLocation`

全文候选 URL。

字段：

```python
url: str
source: str
kind: str
status: FulltextStatus
license: str | None
version: str | None
host_type: str | None
confidence: float
reason: str | None
```

### `PaperSearchResult`

搜索最终结果。

字段：

```python
status: str
message: str
plan: SearchPlan | None
candidates: list[PaperCandidate]
selected: list[PaperCandidate]
```

---

## 5. Query Analyzer

### `paperos.search.query.analyzer.AstrBotLLMQueryAnalyzer`

使用 AstrBot 已配置的大模型，把自然语言 query 转换为 `SearchPlan`。

#### 构造

```python
analyzer = AstrBotLLMQueryAnalyzer(
    context=astrbot_context,
    cfg=PaperOSConfig,
)
```

#### `async analyze(raw_query: str, *, event=None) -> SearchPlan`

黑盒行为：

1. 如果 `cfg.query_analyzer.enabled == False`，走 fallback。
2. 解析 provider id：
   - `cfg.query_analyzer.provider_id`
   - `cfg.general.default_provider_id`
   - 当前会话 provider
3. 调用 AstrBot：
   ```python
   await context.llm_generate(chat_provider_id=provider_id, prompt=prompt)
   ```
4. 从模型输出中提取 JSON。
5. 调用 `parse_search_plan(...)` 转成 `SearchPlan`。
6. 失败时 fallback。

#### `async repair(raw_query, previous_plan, failure_reason, *, event=None) -> SearchPlan`

metadata provider 零候选时可调用。  
作用：让 LLM 根据失败原因生成修复后的 `SearchPlan`。

注意：

- 只允许少量修复轮数，由 `cfg.query_analyzer.max_repair_rounds` 控制。
- repair 不能无限循环。

### `paperos.search.query.fallback.fallback_analyze(raw_query: str) -> SearchPlan`

LLM 不可用或失败时的规则解析器。  
它不追求最佳效果，只保证搜索模块可用。

### `paperos.search.query.schema.parse_search_plan(data, raw_query, max_hypotheses) -> SearchPlan`

把 LLM JSON dict 转成强类型 `SearchPlan`。  
负责枚举值容错、默认值补齐、hypothesis 数量限制。

---

## 6. Provider 接口

Provider 接口在：

```python
paperos.search.providers.base
```

### `MetadataProvider`

```python
class MetadataProvider(ABC):
    name: str

    async def search(self, plan: SearchPlan) -> list[PaperCandidate]:
        ...
```

职责：根据 `SearchPlan` 返回候选论文 metadata。

不应做：

- 候选全局去重。
- 全局消歧。
- 下载 PDF。
- 写数据库。
- 格式化聊天输出。

### `FulltextProvider`

```python
class FulltextProvider(ABC):
    name: str

    async def resolve(self, paper: PaperCandidate) -> list[FulltextLocation]:
        ...
```

职责：根据一篇 `PaperCandidate` 返回全文候选 URL。

不应做：

- 证明 URL 是 PDF。
- 绕过权限。
- 下载落盘。
- 解析 PDF。

---

## 7. CORE Provider

### `paperos.search.providers.core.client.CoreClient`

CORE API HTTP client。内部使用 `httpx.AsyncClient`。

#### `async search_works(q: str, *, limit: int, offset=0, sort=None) -> list[PaperCandidate]`

调用 CORE works search。

输入：

- `q`: CORE 查询语句。
- `limit`: 返回数量，内部限制 1~100。
- `offset`: 分页偏移。
- `sort`: relevance / recency。

输出：

- `list[PaperCandidate]`

可能抛出：

- `CoreAPIError`

#### `async get_work(core_id: str) -> PaperCandidate | None`

按 CORE ID 获取单篇 work。

#### `async aclose() -> None`

关闭 HTTP client。

### `paperos.search.providers.core.metadata_provider.CoreMetadataProvider`

实现 `MetadataProvider`。

#### `async search(plan: SearchPlan) -> list[PaperCandidate]`

黑盒行为：

1. 根据 `plan` 调用 `build_core_queries(plan)`。
2. 对每个 CORE query 调用 `CoreClient.search_works(...)`。
3. 聚合返回所有候选。
4. 某个 query 失败时记录 warning 并继续下一个 query。

### `paperos.search.providers.core.query_builder.build_core_queries(plan: SearchPlan) -> list[str]`

把 `SearchPlan` 转成 CORE query list。

职责：

- DOI → `doi:"..."`
- arXiv → `arxivId:"..."` 和 DOI fallback
- title/fuzzy_title → title query / free-text query
- topic → title/abstract query
- search_queries → 原样追加
- 去重并保持顺序

### `paperos.search.providers.core.fulltext_provider.CoreFulltextProvider`

实现 `FulltextProvider`。

#### `async resolve(paper: PaperCandidate) -> list[FulltextLocation]`

黑盒行为：

- 如果 `paper.download_url` 存在，返回 pdf candidate。
- 如果 `paper.landing_url` 存在且不同于 download_url，返回 landing candidate。
- 不进行 HTTP 验证。

---

## 8. Resolve 层

### `paperos.search.resolve.candidate_resolver.CandidateResolver`

聚合多个 metadata providers。

#### `async resolve(plan: SearchPlan) -> list[PaperCandidate]`

对每个 provider 调用：

```python
provider.search(plan)
```

并聚合所有候选。

### `paperos.search.resolve.scoring.score_candidates(plan, candidates) -> list[PaperCandidate]`

为候选论文设置：

- `candidate.score`
- `candidate.score_reason`

并按分数降序排序。

黑盒原则：

- 精确标题、DOI、arXiv、话题关键词、引用数、全文 URL 等都会影响分数。
- 外部不应依赖具体分数公式，只应理解分数越高越可信。

### `paperos.search.resolve.dedup.PaperDeduplicator`

#### `dedup(candidates: list[PaperCandidate]) -> list[PaperCandidate]`

按以下优先级生成去重 key：

1. DOI
2. arXiv ID
3. CORE ID
4. normalized title

重复时保留质量更高的候选。

### `paperos.search.resolve.disambiguator.PaperDisambiguator`

#### `select(plan, candidates) -> list[PaperCandidate]`

选择最终论文。

规则：

- topic_discovery / find_multiple / expand_related：返回前 `plan.final_limit` 篇。
- find_specific / download_known：
  - top1 分数必须 >= `accept_min_score`
  - top1 和 top2 分差必须 >= `ambiguous_gap_threshold`
  - 否则返回空列表，表示 ambiguous，需要用户确认。

---

## 9. Acquire 层

### `paperos.search.acquire.fulltext_resolver.FulltextResolver`

聚合多个 fulltext providers。

#### `async resolve(paper: PaperCandidate) -> list[FulltextLocation]`

对每个 fulltext provider 调用：

```python
provider.resolve(paper)
```

然后按 URL 去重、按 confidence 降序排序。

### `paperos.search.acquire.verifier.FulltextVerifier`

轻量验证全文 URL。不会绕过权限。

#### `async verify(loc: FulltextLocation, paper: PaperCandidate) -> FulltextLocation`

黑盒行为：

1. 非 http/https → invalid。
2. HTTP 401/403 → requires_auth。
3. HTTP >= 400 → failed。
4. PDF magic bytes 或 `application/pdf` → verified_pdf。
5. `text/html` → html_fulltext 或 landing_only。
6. 其他 → invalid。

### `paperos.search.acquire.downloader.FulltextDownloader`

当前预留给未来 storage/acquisition。  
如果存在，通常职责是下载 verified PDF、计算 sha256、写入文件系统。当前主搜索命令路径不应依赖它。

---

## 10. Presenter

### `paperos.search.presenter.PaperSearchPresenter`

把搜索结果转换为聊天文本。

#### `format_config() -> str`

返回当前关键配置摘要。

#### `format_search_result(result: PaperSearchResult, *, compact=False) -> str`

把 `PaperSearchResult` 格式化为普通聊天输出。

#### `format_candidate(cand: PaperCandidate, *, i=None, compact=False) -> str`

格式化单个候选论文。

注意：

- Presenter 是 UI/输出层，不应参与搜索、打分、去重、下载。
