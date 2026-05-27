# PaperOS API Index

## Search

- `paperos.search.service.PaperSearchService.search(raw_query, event=None, need_fulltext=True)`
  - 在线查找论文候选并尽力验证 PDF。
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

## RAG

RAG 只读本地 storage，不调用 search。若本地没有论文，应由用户显式调用 `/paperos search` 或未来的 `/paperos add`。
