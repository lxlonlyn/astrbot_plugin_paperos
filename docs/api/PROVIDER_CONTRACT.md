# PaperOS Provider Contract

本文件定义 `paperos/search/providers/` 的扩展规范。  
后续接入 OpenAlex、Crossref、Semantic Scholar、Unpaywall、ACM、arXiv 等 API 时，优先遵守本文件。

## 两类 Provider

### MetadataProvider

负责把 `SearchPlan` 转成外部 API 请求，并返回 `PaperCandidate`。

```python
from paperos.search.providers.base import MetadataProvider

class MyMetadataProvider(MetadataProvider):
    name = "my_provider"

    async def search(self, plan: SearchPlan) -> list[PaperCandidate]:
        ...
```

### FulltextProvider

负责根据 `PaperCandidate` 提出全文候选 URL，并返回 `FulltextLocation`。

```python
from paperos.search.providers.base import FulltextProvider

class MyFulltextProvider(FulltextProvider):
    name = "my_provider"

    async def resolve(self, paper: PaperCandidate) -> list[FulltextLocation]:
        ...
```

## MetadataProvider 必须遵守

### 应做

- 使用 `SearchPlan` 和 `PaperHypothesis` 构建 API query。
- 返回尽可能完整的 `PaperCandidate`。
- 把 provider 原始响应放入 `candidate.raw`。
- 设置 `candidate.source = provider.name`。
- 捕获单次 query 失败，记录 warning，尽可能继续其他 query。
- 控制返回数量，遵守 `plan.max_candidates` 或 provider 自己的安全上限。

### 不应做

- 不做全局去重。去重由 `PaperDeduplicator` 负责。
- 不做最终消歧。消歧由 `PaperDisambiguator` 负责。
- 不下载 PDF。
- 不写数据库。
- 不格式化聊天输出。
- 不把 LLM 输出当作事实直接返回。

## FulltextProvider 必须遵守

### 应做

- 从 `PaperCandidate` 中的 DOI、arXiv ID、publisher link、OA location、download URL 等字段生成候选 URL。
- 返回 `FulltextLocation`。
- 设置 `source`、`kind`、`confidence`、`reason`。
- 尽可能保留 license、version、host_type 等信息。

### 不应做

- 不证明 URL 一定可用。验证由 `FulltextVerifier` 负责。
- 不绕过 paywall、登录、验证码。
- 不批量爬取出版社。
- 不写数据库。
- 不下载文件到本地。

## Provider 注册方式

在 `PaperSearchService.__init__` 中注册：

```python
self.metadata_resolver = CandidateResolver(
    providers=[
        CoreMetadataProvider(self.core_client),
        OpenAlexMetadataProvider(self.openalex_client),
        CrossrefMetadataProvider(self.crossref_client),
    ]
)

self.fulltext_resolver = FulltextResolver(
    providers=[
        CoreFulltextProvider(self.core_client),
        UnpaywallFulltextProvider(self.unpaywall_client),
        OpenAlexFulltextProvider(self.openalex_client),
    ]
)
```

外部模块不应直接访问 provider。

## Candidate 字段填充建议

### 强烈建议填

```python
title
authors
year
doi
source
raw
```

### 尽量填

```python
venue
publisher
abstract
citation_count
download_url
landing_url
arxiv_id
```

### provider 专属 ID

```python
core_id
openalex_id
semantic_scholar_id
```

没有对应 ID 就留空。

## FulltextLocation 字段填充建议

```python
FulltextLocation(
    url="https://...",
    source="openalex",
    kind="pdf",           # pdf/html/landing
    confidence=0.8,
    reason="OpenAlex best_oa_location.pdf_url",
    license="cc-by",
    version="publishedVersion",
    host_type="repository",
)
```

## 日志规范

Provider 层使用 AstrBot logger：

```python
from astrbot.api import logger
```

推荐日志：

```python
logger.debug(
    "[PaperOS][OpenAlexMetadataProvider] executing %d queries: %s",
    len(queries),
    short_query_list,
)

logger.warning(
    "[PaperOS][OpenAlexMetadataProvider] query failed q=%r error=%s",
    query,
    exc,
)
```

不要在 debug log 中直接打印完整 API 响应、大摘要、全文 HTML 或大型候选列表。
