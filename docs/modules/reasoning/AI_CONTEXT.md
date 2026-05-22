# PaperOS Reasoning：AI Context

Reasoning 是未来用于论文理解、claim 组织、实验记录和科研记忆的模块。

## 职责

- 基于 RAG 上下文进行论文问答。
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

这些不应阻塞 storage/ingest 第一阶段。
