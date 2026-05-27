# PaperOS Reasoning：AI Context

Reasoning 不再作为论文数据链路的独立顶层模块。论文理解、claim 组织、idea generation、实验记录和科研记忆应优先作为 `rag` 的上层 analysis workflow。

## 职责

- 基于 RAG 上下文进行论文问答和分析。
- 抽取 method / claim / experiment / limitation / related work。
- 组织长期科研笔记。
- 与用户项目上下文交互。

## 不负责

- 外部搜索。
- 下载 PDF。
- SQLite schema 底层维护。
- 向量索引底层维护。

## 未来可能的数据结构

- `claims`
- `paper_claim_links`
- `concepts`
- `concept_aliases`
- `paper_concept_edges`
- `experiment_notes`

这些不应阻塞 search/storage/rag 的核心数据链路。
