# PaperOS API Index

## Search

- `paperos.search.service.PaperSearchService.search(raw_query, event=None, need_fulltext=True)`
  - 在线查找论文候选并尽力下载、验证 PDF。
  - 不写数据库。
  - 不构建 embedding。
  - QueryAnalyzer 可在 AstrBot 会话启用 `provider_settings.web_search` 时受控调用 AstrBot 内置 web-search 工具补充 URL 证据。

- `paperos.search.models.PaperSearchResult`
  - `status`: `selected` / `ambiguous` / `not_found` / `disabled` / `error`
  - `candidates`: 所有候选
  - `selected`: 自动选中的候选；主题搜索可能多篇

## Storage

- `paperos.storage.interfaces.LocalPaperRepository`
  - 本地论文库协议。
  - 不联网。
  - 使用 `paperos.storage.models.PaperRecordDraft`。

- `paperos.storage.interfaces.ObjectStore`
  - 接收 bytes 或本地 file。
  - 返回 `StoredObject`。

- `paperos.workflows.search_storage.SearchStorageImportWorkflow.import_search_result(result, source_query=None)`
  - search/storage/RAG-job 边界 workflow。
  - upsert paper metadata。
  - 将 verified PDF 归档到 object store。
  - 注册 object/version/fulltext-location link。
  - 可选地入队 `rag_index_pdf`；实际 parser/chunker/indexer 属于 RAG workflow。
  - 已接入 `/paperos search` 的 AstrBot command workflow。

## AstrBot Commands

- `/paperos search <query>`
  - 调用 search。
  - storage 启用时自动导入同一次搜索结果，归档 verified PDF，入队 `rag_index_pdf`。
  - 发送文件时优先使用 storage object 路径。

- `/paperos storage status`
  - 返回 storage 目录、schema、对象库、统计和 job 状态。

- `/paperos storage info <paper_id|doi|arxiv|title>`
  - 查询本地论文、identifier、object、verified PDF、chunk、index status 和最近 jobs。

## RAG

RAG 从本地 storage 读取 paper/object/chunk/index 数据，不调用 search。它负责解析、chunk、embedding、index、retrieval 和基于本地证据的分析。若本地没有论文，应由用户显式调用 search 相关命令或上层 workflow 先扩充本地库。
