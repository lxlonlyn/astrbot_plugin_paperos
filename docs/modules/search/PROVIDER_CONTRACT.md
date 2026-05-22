# Search Provider Contract

本文档说明后续接入 OpenAlex / Crossref / Semantic Scholar / Unpaywall 等 provider 时应遵守的契约。

## MetadataProvider

```python
async def search(plan: SearchPlan) -> list[PaperCandidate]: ...
```

要求：

- 只返回 provider 可验证的 metadata。
- 不把 LLM 猜测字段当成事实。
- DOI、arXiv、CORE、OpenAlex、Semantic Scholar 等外部 ID 应尽量规范化。
- 不下载 PDF bytes。

## FulltextProvider

```python
async def resolve(paper: PaperCandidate) -> list[FulltextLocation]: ...
```

要求：

- 只提出 PDF / HTML / landing URL candidate。
- 不持久化文件。
- 不绕过权限。
- 不把 landing page 伪装成 PDF。

## FulltextVerifier

负责轻量 URL 类型验证：

- HTTP status。
- content-type。
- 前若干字节 magic bytes，例如 `%PDF-`。

不负责：

- 完整下载。
- 文件完整性校验。
- 本地 object registration。
