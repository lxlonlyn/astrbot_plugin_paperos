# Search API

## PaperSearchService

稳定外部入口。其他模块优先只依赖它。

```python
result = await PaperSearchService.search(
    raw_query: str,
    event=None,
    need_fulltext: bool = True,
)
```

返回：`PaperSearchResult`。

### 使用场景

- 用户明确要找论文。
- `PaperSearchService` 本身只发现候选；AstrBot command/workflow 会在同一次 `/paperos search` 中决定是否写入 storage。
- 显式的“扩充本地论文库”流程需要先发现并验证候选。

### 不推荐外部调用的内部类

- `PaperSearchPipeline`：流程编排，内部实现细节。
- `TargetedPaperCrawler`：只跟进明确来源的实现细节。
- `DomainResolver`：站点 URL 归一化实现细节。
- `FulltextVerifier`：下载并严格验证 PDF 的实现细节。
- `CoreClient` / `paperos.search.providers.*`：legacy provider 代码，当前默认 search path 不使用。

## PaperSearchResult

关键字段：

- `status`: `disabled` / `not_found` / `selected` / `ambiguous` / `error`
- `message`
- `plan`
- `candidates`
- `selected`

使用规则：

```python
if result.selected:
    paper = result.selected[0]
elif result.status == "ambiguous":
    # 需要用户确认或让上层 workflow 谨慎处理
else:
    # not_found / error
```

## 判断是否有 verified PDF

```python
from paperos.search.models import FulltextStatus

verified = [
    loc for loc in paper.fulltext_locations
    if loc.status == FulltextStatus.VERIFIED_PDF
]
```

注意：`VERIFIED_PDF` 表示该候选已经被下载到 searcher 临时目录并通过本地 PDF 校验；它仍不是长期入库状态。`/paperos search` 的 command workflow 会在 storage 启用时调用 `SearchStorageImportWorkflow` 和 storage object store 归档。
