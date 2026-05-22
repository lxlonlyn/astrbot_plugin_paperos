# Storage API

本文档描述 storage 模块对外 facade。具体类名可以随实现调整，但外部应只依赖这些概念，不直接散落 SQL。

## create_storage_context

推荐稳定入口：

```python
storage = await create_storage_context(cfg, plugin_name=plugin_name)
```

返回对象建议包含：

```python
storage.repository
storage.object_store
storage.paths
```

使用规则：

- `main.py` 或插件生命周期中初始化一次。
- service 之间传递 context 或 repository，不重复解析路径。
- 插件关闭时调用 `await storage.aclose()`。

## Repository

Repository 封装 SQLite 操作。

### upsert_candidate

```python
paper_id = await repo.upsert_candidate(
    candidate,
    source_query=raw_query,
    decision="auto_selected",
)
```

职责：

- 规范化 candidate metadata。
- 按 identifier 查重。
- 必要时按 title/year/author 做本地模糊查重。
- 创建或更新 `papers`。
- 写入 `paper_identifiers`。
- 写入 `paper_aliases`。
- 写入 `fulltext_locations`。

不负责：

- 下载 PDF。
- 解析 PDF。

### enqueue_job

```python
job_id = await repo.enqueue_job(
    job_type="download_pdf",
    dedupe_key=f"download_pdf:{paper_id}:{url}",
    paper_id=paper_id,
    payload={"url": url},
)
```

要求：

- `job_type + dedupe_key` 应唯一，避免重复任务。
- 支持 pending/running/succeeded/failed/cancelled。
- 支持 stale lock 恢复。

### register_object

```python
object_id = await repo.register_object(stored_object)
```

对象由 `ObjectStore` 写入后，再由 repository 记录 metadata。

### attach_object_to_paper

```python
await repo.attach_object_to_paper(
    paper_id=paper_id,
    object_id=object_id,
    role="pdf",
)
```

## ObjectStore

ObjectStore 管理本地文件系统中的大对象。

推荐接口：

```python
stored = await object_store.put_file(
    src_path,
    kind="pdf",
    suffix=".pdf",
)
```

职责：

- 写入 tmp。
- 计算 sha256。
- atomic rename。
- 生成 storage key。
- 返回 size/mime/sha256/storage_key。

不负责：

- 写 paper/version 关系。
- 判断该 PDF 属于哪篇论文。
