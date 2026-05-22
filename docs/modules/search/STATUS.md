# Search Status

## 已实现

- LLM query analyzer。
- CORE metadata provider。
- 候选 scoring。
- search-stage dedup。
- disambiguation。
- fulltext location resolve。
- fulltext URL lightweight verification。
- presenter 格式化。

## 未实现

- 多 provider 聚合。
- 本地 storage 入库。
- PDF 下载落盘。
- PDF 解析、chunk、embedding。
- RAG retrieval。

## 重要边界

searcher 已经可以较好地找到准确论文和 PDF URL，但它不拥有长期本地状态。长期状态必须交给 storage/ingest。
