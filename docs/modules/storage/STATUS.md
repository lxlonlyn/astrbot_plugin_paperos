# Storage Status

## 当前状态

storage 处于待落地或早期接口阶段。当前重点应是建立最小稳定闭环，而不是一次性实现完整 RAG。

## 第一阶段应实现

- 配置读取。
- 数据目录初始化。
- SQLite schema + migrations。
- Repository facade。
- ObjectStore facade。
- 内部 ID 生成。
- candidate upsert。
- local dedup。
- fulltext location register。
- job enqueue/claim/finish。
- object register/link。

## 暂不作为第一阶段目标

- PDF 版面解析。
- 公式/表格/图片抽取。
- LanceDB 实装。
- concept graph。
- 多人同步。
- 外置数据库。

## 风险点

- 不要用 `sha256`、DOI、arXiv ID 作为 `paper_id`。
- 不要让 search pipeline 直接写 SQLite。
- 不要让 provider 下载 PDF。
- 不要把数据库放在插件源码目录。
- 不要在没有 migration 的情况下直接修改 schema。
