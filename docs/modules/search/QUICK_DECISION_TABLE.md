# Search 快速决策表

## 我想搜索论文

```python
await PaperSearchService.search(raw_query, event=event, need_fulltext=True)
```

不要直接调 `CoreClient`。

## 我想只要 metadata，不验证全文

```python
await PaperSearchService.search(raw_query, event=event, need_fulltext=False)
```

## 我想把搜索结果显示给用户

```python
text = PaperSearchPresenter(cfg).format_search_result(result)
```

不要在 `main.py` 或其他模块手写格式化。

## 我想新增一个搜索 API

实现：

```python
MetadataProvider.search(plan) -> list[PaperCandidate]
```

然后在 `PaperSearchService` 组装。

## 我想新增一个 PDF/OA 来源

实现：

```python
FulltextProvider.resolve(paper) -> list[FulltextLocation]
```

然后在 `PaperSearchService` 组装。

## 我想下载 PDF

不要放进 search provider。应由 future `paperos/ingest/download.py` 或 downloader service 处理。

## 我想存数据库

不要放进 search pipeline。应调用 storage repository 或 ingest service。
