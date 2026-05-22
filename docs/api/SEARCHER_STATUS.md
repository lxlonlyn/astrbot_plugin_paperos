# PaperOS Searcher 当前实现状态

本文件说明当前 searcher 已实现、未实现和边界。  
未来对话遇到“是否已经支持 X”时，优先看这里。

## 已实现

### AstrBot 集成

- `/paperos search ...` 命令。
- `/paperos config` 命令。
- `paperos_search_paper` LLM tool。
- 使用 AstrBot `event.message_str` 获取完整 query。
- 使用 AstrBot `context.llm_generate(...)` 调用已配置模型。
- 使用 AstrBot `logger` 输出日志。

### QueryAnalyzer

- LLM QueryAnalyzer。
- fallback 规则解析。
- metadata provider 零候选时的 repair 机制。
- provider 选择顺序：
  - query_analyzer.provider_id
  - general.default_provider_id
  - 当前会话 provider

### CORE metadata search

- CORE `search/works` 查询。
- CORE `works/{id}` 查询。
- CORE work → `PaperCandidate` 转换。
- DOI、arXiv、title、topic、search_queries 等 query 构建。

### Resolve

- 多 provider 聚合接口。
- 候选 scoring。
- DOI/arXiv/CORE/title 去重。
- find_specific 自动接受与 ambiguous 判断。
- topic/multiple/expand_related 返回前 `final_limit`。

### Fulltext candidate

- 从 CORE `download_url` 生成 PDF candidate。
- 从 CORE `landing_url` 生成 landing candidate。
- 多 fulltext provider 聚合接口。
- URL 去重和 confidence 排序。

### Fulltext verification

- HTTP range/partial GET 轻量验证。
- PDF magic bytes / content-type 判断。
- HTML article / landing 粗分。
- 401/403 标记 requires_auth。
- 不绕过权限。

## 未实现

### 数据库

尚未实现：

- SQLite schema。
- paper metadata 入库。
- search history 入库。
- candidate cache。
- local paper repository。
- 本地重复论文检测。
- 本地 PDF 文件记录。
- 本地向量/RAG index 状态记录。

### PDF 下载与文件存储

尚未接入主流程：

- 下载 verified PDF 到本地。
- 计算 PDF sha256 并作为文件 ID。
- 保存文件路径。
- 验证 PDF 页数。
- 从 PDF 抽取 title/DOI 二次校验。
- 断点续传。
- PDF 下载失败重试队列。

### RAG / 阅读 / 思考

尚未实现：

- PDF 解析。
- markdown/text extraction。
- chunk。
- embedding。
- vector index。
- paper reasoning。
- related work 自动总结。
- claim extraction。

### 多搜索源

当前 provider 接口已经准备好，但实际只接入：

- CORE

尚未接入：

- OpenAlex
- Crossref
- Semantic Scholar
- Unpaywall
- arXiv
- ACM/CVF/PMLR 等 publisher resolver

## 当前搜索结果的可信度边界

- LLM 只生成 SearchPlan/hypothesis，不代表事实正确。
- CORE 返回的 metadata 仍可能重复、缺字段、没有 PDF。
- `verified_pdf` 只表示 URL 返回内容看起来是 PDF，不表示已经下载入库。
- `landing_only` 不代表失败，只代表当前没有自动确认 PDF。
- `requires_auth` 不应尝试绕过权限。

## 推荐下一步

优先顺序：

1. 添加 storage 层接口与 SQLite schema。
2. 添加 `/paperos ingest ...`，不要让 `/paperos search ...` 默认入库。
3. 接入 Unpaywall / OpenAlex fulltext provider，提高非 arXiv 论文覆盖。
4. 接入 Crossref metadata provider，提高 DOI 和 publisher 信息质量。
5. 添加 PDF downloader + sha256 + file_store。
6. 添加 PDF 解析与 RAG。
