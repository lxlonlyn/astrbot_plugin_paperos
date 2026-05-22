# PaperOS API 文档索引

> 面向未来对话、协作者、代码智能体的黑盒文档。  
> 目标：优先阅读这些文档理解模块边界和函数作用；只有文档不能回答具体实现问题时，才回退到源码。

## 阅读顺序

1. [`docs/api/AI_CONTEXT_SEARCHER.md`](api/AI_CONTEXT_SEARCHER.md)  
   给 ChatGPT / 代码智能体的压缩上下文。适合开启新对话时先贴进去。

2. [`docs/api/SEARCHER_API.md`](api/SEARCHER_API.md)  
   搜索模块 API Reference。说明每个公开类/函数的职责、输入、输出、是否推荐直接调用。

3. [`docs/api/PROVIDER_CONTRACT.md`](api/PROVIDER_CONTRACT.md)  
   后续接入 OpenAlex / Crossref / Semantic Scholar / Unpaywall 等 provider 时优先看这里。

4. [`docs/api/SEARCHER_STATUS.md`](api/SEARCHER_STATUS.md)  
   当前已经实现和没有实现的边界，特别是数据库、PDF 下载、全文验证等。

## 当前稳定调用入口

外部模块，包括 AstrBot handler、RAG、reasoning、未来 ingestion，优先只调用：

```python
await PaperSearchService.search(raw_query, event=event, need_fulltext=True)
```

不要直接调用 CORE client、QueryAnalyzer、Pipeline 或 provider，除非你正在开发搜索模块内部。

## 模块边界

```text
main.py
  AstrBot 入口；只处理命令、tool 注册、用户消息解析、结果展示。

paperos/search/service.py
  搜索模块对外门面；负责构造依赖并暴露稳定 API。

paperos/search/pipeline.py
  搜索流程编排；负责 QueryAnalyzer → metadata resolve → scoring/dedup → disambiguation → fulltext resolve/verify。

paperos/search/query/
  自然语言到 SearchPlan 的解析。LLM 只产生 hypothesis，不负责事实验证。

paperos/search/providers/
  外部学术 API 的适配层。当前实现 CORE，未来扩展其他 provider。

paperos/search/resolve/
  候选论文的合并、打分、去重、消歧。

paperos/search/acquire/
  全文候选 URL 的收集、验证、未来下载。当前不负责数据库入库。

paperos/search/presenter.py
  把 PaperSearchResult 格式化成聊天输出。
```

## 使用原则

- LLM 输出是“检索假设”，不是事实。
- Provider 输出是“候选论文”，仍需打分、去重、消歧。
- FulltextProvider 只提出 URL，不证明 URL 可用。
- FulltextVerifier 只验证 URL 类型和可访问性，不绕过权限。
- 当前 searcher 不负责 SQLite 入库，不负责真正下载 PDF 落盘，不负责 RAG chunk/embedding。
