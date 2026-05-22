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
- ingest 模块需要先发现候选。
- RAG 模块需要在本地没有结果时触发外部发现。

### 不推荐外部调用的内部类

- `PaperSearchPipeline`：流程编排，内部实现细节。
- `CoreClient`：具体 provider client。
- `FulltextVerifier`：URL 类型验证工具，不等价于下载器。

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
    # 需要用户确认或让 ingest 策略谨慎处理
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

注意：`VERIFIED_PDF` 表示 URL 轻量验证像 PDF，不表示已经下载、保存或解析。
