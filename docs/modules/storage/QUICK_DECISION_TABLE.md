# Storage 快速决策表

## 我想初始化本地数据库

调用 storage facade：

```python
storage = await create_storage_context(cfg, plugin_name=self.name)
```

不要在 `main.py` 手动拼 SQLite 路径和执行 SQL。

## 我想把搜索结果入库

调用 search/storage workflow，或先把 search DTO 转成 storage DTO 后调用 repository：

```python
workflow = SearchStorageImportWorkflow(repository=repo, object_store=store)
summary = await workflow.import_search_result(result, source_query=query)
```

不要让 `PaperSearchPipeline` 写数据库。也不要拆成 `/paperos add` 后再次 search；入库应消费同一次 `/paperos search` 产生的 `PaperSearchResult`。

## 我想保存 PDF 文件

searcher 已经验证并下载的 PDF，可以交给 object store 归档：

```python
stored = await object_store.put_file(verified_pdf_path, kind="pdf", suffix=".pdf")
object_id = await repo.register_object(stored)
await repo.attach_object_to_current_version(paper_id=paper_id, object_id=object_id, role="pdf")
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

## 我想提交后续处理任务

当前 searcher 已负责临时 PDF 下载和验证。storage 只记录任务状态；解析、chunk、embedding、index 的执行方应在 RAG workflow：

```python
await repo.enqueue_job(
    job_type="rag_index_pdf",
    dedupe_key=f"rag_index_pdf:{object_id}",
    paper_id=paper_id,
    object_id=object_id,
    payload={"source_query": query},
)
```

## 我想做 RAG 检索

storage 只提供 chunks、object path、job 和 index status 的持久化接口。parser、chunker、embedding、retrieval、analysis 都放到 `paperos/rag/`。
