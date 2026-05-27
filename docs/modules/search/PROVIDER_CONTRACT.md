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

负责把候选全文 URL 下载到本地临时目录，并严格验证它确实是可读 PDF：

- HTTP status。
- content-type。
- 前若干字节 magic bytes，例如 `%PDF-`。
- 按 `search_policy.max_pdf_size_mb` 限制下载大小。
- 下载到 AstrBot 规定的插件数据目录：
  `get_astrbot_data_path()/plugin_data/astrbot_plugin_paperos/searcher/fulltext/`。
- 以 SHA-256 命名最终 PDF，避免重复下载同一文件。
- 使用 `pypdf` 打开本地文件并验证页数大于 0。

不负责：

- 本地 object registration。
- 长期归档。
- PDF 文本解析、chunk、embedding。
- 绕过登录、验证码、paywall 或出版社权限限制。

`FulltextStatus.VERIFIED_PDF` 只表示 search 阶段临时文件已经下载并通过本地 PDF 校验；长期保存应由 storage object store 接管。
