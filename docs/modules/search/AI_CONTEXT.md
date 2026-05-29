# PaperOS Search：AI Context

本文件是给 ChatGPT / 代码智能体优先阅读的 search 模块黑盒上下文。它说明模块职责、稳定入口、重要数据结构和扩展规则，不追求覆盖源码细节。

## 当前任务边界

`paperos/search/` 只负责“论文搜索与全文候选验证”。

当前 searcher 已实现：

- 从 AstrBot 命令或 LLM tool 接收自然语言 query。
- 用 AstrBot 已配置的大模型把 query 解析成结构化 `SearchPlan`，中文提问也应转换成英文论文标题、英文 topic keywords 和英文查询描述。
- 如果当前 AstrBot 会话启用了 `provider_settings.web_search`，QueryAnalyzer 先用普通 `context.llm_generate(...)` 生成英文 `SearchPlan`，再由 PaperOS 代码直接调用 AstrBot 已配置 provider 的单个内置网页搜索工具。该阶段不使用 `tool_loop_agent(...)`，不注入页面抽取工具，搜索 query 数量受 `query_analyzer.max_web_search_queries` 控制且硬上限为 5；返回 URL 后续交给 crawler/verifier 处理。
- 在 LLM 不可用或解析失败时，用 fallback analyzer 识别 DOI、arXiv ID、URL；如果只剩中文标题/主题，不直接拿中文去站点 lookup。
- 用 targeted crawler 跟进 SearchPlan 中已有的明确来源。
- 对 arXiv、ACM DL、OpenReview、ACL Anthology、直接 PDF URL 等已知来源做 URL 归一化。
- 对具体英文文章标题做小范围站点 lookup：arXiv API 与 ACM DL 站内检索。该路径用于已知论文名，不是通用网页搜索或会议批量爬虫。
- 对 LLM 提供的 DOI/arXiv/URL 做标题反校验；如果抓回来的标题与计划标题不匹配，视为 planner 幻觉的 bad identifier，不让它压制标题 lookup 候选。
- 对候选做 scoring、dedup、disambiguation。
- 从 HTML citation meta、已知站点规则或直接链接中提取 PDF / landing URL。
- 下载候选 PDF 到 AstrBot 插件数据目录下的 searcher 临时目录，并用文件头、大小限制、SHA-256 去重和 `pypdf` 做严格验证。
- 标记 `verified_pdf` / `no_open_access` / `requires_auth` / `failed` / `invalid` 等全文状态。
- 返回 `PaperSearchResult`，由 presenter 格式化为聊天输出。

当前 searcher 不实现：

- SQLite / LanceDB / 本地数据库入库。
- 将 searcher 临时 PDF 归档为长期 storage object。
- PDF 解析、chunk、embedding、RAG。
- 自己维护一套独立的通用网页搜索后端或会议/期刊批量爬虫；网页搜索应优先复用 AstrBot 内置搜索工具。
- CORE/OpenAlex/Semantic Scholar 等学术 API 默认主链路。
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
- `TargetedPaperCrawler`
- `DomainResolver`
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
TargetedPaperCrawler.discover()
  ↓
DomainResolver.fulltext_from_url()
  ↓
score_candidates()
  ↓
PaperDeduplicator.dedup()
  ↓
PaperDisambiguator.select()
  ↓
FulltextVerifier.verify()
  ↓
PaperSearchResult
```

## 与 storage / rag 的关系

- search 返回候选、fulltext 状态和 searcher 临时 PDF 路径。
- searcher 临时 PDF 必须放在 AstrBot 插件数据目录：`get_astrbot_data_path()/plugin_data/astrbot_plugin_paperos/searcher/fulltext/`。
- 上层 command/workflow 或 library facade 消费 search 结果，决定是否入库。
- storage 负责 paper/version/object/job 的长期状态。
- storage object store 负责把 verified PDF 从临时路径归档为长期 object。
- rag 负责后续 PDF 解析、chunk、embedding、index 和本地分析。
