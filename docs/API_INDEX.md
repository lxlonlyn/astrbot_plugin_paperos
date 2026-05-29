# PaperOS API Index

## Search

- `paperos.search.service.PaperSearchService.search(raw_query, event=None, need_fulltext=True)`
  - 在线查找论文候选并尽力下载、验证 PDF。
  - 不写数据库。
  - 不构建 embedding。

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
  - 注册 object/version link。
  - 可选地入队 RAG 后续处理 job；实际 parser/chunker/indexer 属于 RAG workflow。
  - 当前尚未接入 `/paperos search`。

## RAG

RAG 从本地 storage 读取 paper/object/chunk/index 数据，不调用 search。它负责解析、chunk、embedding、index、retrieval 和基于本地证据的分析。若本地没有论文，应由用户显式调用 search 相关命令或上层 workflow 先扩充本地库。
