# Storage 快速决策表

## 我想初始化本地数据库

调用 storage facade：

```python
storage = await create_storage_context(cfg, plugin_name=self.name)
```

不要在 `main.py` 手动拼 SQLite 路径和执行 SQL。

## 我想把搜索结果入库

调用 repository：

```python
paper_id = await repo.upsert_candidate(candidate, source_query=query)
```

不要让 `PaperSearchPipeline` 写数据库。

## 我想保存 PDF 文件

先由 downloader 完整下载到临时文件，再交给 object store：

```python
stored = await object_store.put_file(tmp_pdf_path, kind="pdf", suffix=".pdf")
object_id = await repo.register_object(stored)
await repo.attach_object_to_paper(paper_id, object_id, role="pdf")
```

不要把 URL 直接当成本地 PDF。

## 我想判断一篇论文是否已存在

优先顺序：

1. `paper_identifiers`: DOI / arXiv / CORE / OpenAlex / Semantic Scholar。
2. `paper_aliases`: normalized title。
3. title + year + first author fuzzy match。
4. 下载后 object sha256 确认。

## 我想只保留最新版本

更新 `papers.current_version_id` 和 `paper_versions.is_current`。旧 object 可以标记 `deleted_at` 或进入 GC，但不要混淆 paper identity。

## 我想提交下载任务

```python
await repo.enqueue_job(
    job_type="download_pdf",
    dedupe_key=f"download_pdf:{paper_id}:{url}",
    paper_id=paper_id,
    payload={"url": url},
)
```

## 我想做 RAG 检索

storage 只提供 chunks 和 index status。具体 retrieval 放到 `paperos/rag/`。
