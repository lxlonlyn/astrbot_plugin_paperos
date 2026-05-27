# Storage 模块

Storage 是 PaperOS 的本地事实源。它不联网，也不调用 LLM。

## 职责

- SQLite schema / migration。
- paper metadata、identifier、alias、version、object、fulltext location、job、chunk、index status。
- content-addressed object store。
- 本地去重。
- 提供 RAG 可读取的 chunk / vector / FTS 状态。

## 边界

Storage 不应该 import `paperos.search.models`。Search 的候选对象应在上层 facade 转换为 `storage.models.PaperRecordDraft` 后再交给 repository。

```text
search.PaperCandidate
  -> facade/adapter converts
  -> storage.PaperRecordDraft
  -> repository.upsert_paper()
```

## 下载边界

Search 负责下载和验证临时 PDF；storage 负责长期保存：

```text
search: local_path=/.../searcher/fulltext/<sha>.pdf
storage.object_store.put_file(local_path, kind="pdf")
storage.repository.register_object(...)
storage.repository.attach_object_to_current_version(...)
```

Storage 不接受 URL 下载任务，只接受已经存在的本地文件或 bytes。

## Embedding 边界

Embedding provider 不属于 storage。推荐放在 `rag/indexer.py` 或未来 worker 中：

```text
storage 读待处理 chunk
rag.indexer 调 embedding provider
storage.vector 写入向量
storage 更新 index_status
```
