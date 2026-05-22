# PaperOS 模块边界

本文档用于避免把职责混进错误模块。

## main.py

负责：

- AstrBot command / tool 注册。
- 用户输入解析。
- 权限、配置读取、生命周期 glue code。
- 调用 service facade。
- 使用 presenter 格式化结果。

不负责：

- 写数据库 SQL。
- 调 CORE / OpenAlex / Crossref 等底层 client。
- 下载 PDF。
- 解析 PDF。
- 构建 embedding。

## search

负责：

- 自然语言 query -> SearchPlan。
- 调学术 metadata provider。
- 对候选论文打分、去重、消歧。
- resolve fulltext URL。
- 对 fulltext URL 做轻量验证。
- 返回 `PaperSearchResult`。

不负责：

- 本地 SQLite 入库。
- PDF bytes 下载。
- 本地 object path 管理。
- PDF 解析、chunk、embedding、RAG。

## storage

负责：

- PaperOS 内部 ID。
- paper / version / identifier / alias / object / job / chunk / index schema。
- SQLite repository。
- 本地 object store。
- 本地去重线索。
- migration 和初始化。

不负责：

- 联网搜索。
- 网络下载。
- PDF 解析。
- embedding 计算。
- RAG answer generation。

## ingest

负责：

- 编排 search 结果入库。
- 调用 storage local dedup。
- 选择 fulltext location。
- 创建 download/parse/chunk/embed job。
- 推进状态机。

不负责：

- 实现 provider 搜索。
- 直接写 SQL 细节。
- 直接持有 vector index 细节。

## rag

负责：

- 本地 FTS / vector / hybrid retrieval。
- rerank。
- chunk 邻接扩展。
- 构造回答上下文。

不负责：

- 论文搜索。
- PDF 下载。
- 数据库 schema migration。

## reasoning

负责：

- 面向论文理解的长任务。
- claim、method、实验、related work 等结构化抽取。
- 与 RAG 结果交互。

不负责：

- 原始论文搜索和文件生命周期。
