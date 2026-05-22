# Searcher 快速决策表

## 我想搜索论文

调用：

```python
await PaperSearchService.search(raw_query, event=event, need_fulltext=True)
```

不要直接调 `CoreClient`。

## 我想只要 metadata，不验证全文

调用：

```python
await PaperSearchService.search(raw_query, event=event, need_fulltext=False)
```

## 我想把搜索结果显示给用户

调用：

```python
text = PaperSearchPresenter(cfg).format_search_result(result)
```

不要在 `main.py` 或其他模块手写格式化。

## 我想新增一个搜索 API

实现：

```python
MetadataProvider.search(plan) -> list[PaperCandidate]
```

然后在 `PaperSearchService` 注册。

## 我想新增一个 PDF/OA 来源

实现：

```python
FulltextProvider.resolve(paper) -> list[FulltextLocation]
```

然后在 `PaperSearchService` 注册。

## 我想判断是否有明确结果

```python
if result.selected:
    # 明确选中
else:
    # ambiguous / not_found
```

## 我想判断是否有可用 PDF

```python
verified = [
    loc for loc in paper.fulltext_locations
    if loc.status == FulltextStatus.VERIFIED_PDF
]
```

## 我想下载 PDF

当前主流程未实现。  
未来应新增 ingestion/acquisition/storage，不要把下载逻辑塞进 provider 或 presenter。

## 我想存数据库

当前未实现。  
未来应新增 storage repository，searcher 只返回 `PaperSearchResult`。

## 我想修改 LLM 如何理解 query

修改：

```text
paperos/search/query/prompts.py
paperos/search/query/schema.py
paperos/search/query/fallback.py
```

## 我想修改候选排序

修改：

```text
paperos/search/resolve/scoring.py
```

## 我想修改自动接受/歧义判断

修改：

```text
paperos/search/resolve/disambiguator.py
```

## 我想修改 CORE 查询语句

修改：

```text
paperos/search/providers/core/query_builder.py
```

## 我想修改 CORE 返回字段解析

修改：

```text
paperos/search/providers/core/client.py::_work_to_candidate()
```
