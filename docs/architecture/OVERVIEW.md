# PaperOS 架构总览

PaperOS 是 AstrBot 插件中的长期论文系统。它不是单一 searcher，而是一组可以逐步落地的模块：搜索、入库、存储、解析、索引、RAG、reasoning。

## 分层目标

```text
User / LLM Tool / AstrBot Command
        ↓
main.py / runtime glue
        ↓
SearchService      IngestService      RagService      ReasoningService
        ↓                ↓                ↓                ↓
providers        storage repo       vector/fts       long-context tasks
        ↓                ↓                ↓                ↓
external APIs    SQLite + files     LanceDB/API      structured outputs
```

## 第一阶段目标

第一阶段不追求完整 RAG，而是优先完成可恢复的本地数据闭环：

```text
search candidate
  -> local dedup
  -> upsert paper metadata
  -> register verified fulltext location
  -> enqueue download job
  -> download pdf
  -> register object
  -> mark current version
```

## 长期目标

```text
PDF / HTML / metadata
  -> parse
  -> chunk
  -> API embedding provider
  -> local vector index
  -> hybrid retrieval
  -> paper QA / claim extraction / project memory
```

## 关键原则

1. Searcher 很强，但只做外部发现与 URL 验证，不拥有本地长期状态。
2. SQLite 是 source of truth；LanceDB、FTS、embedding index 都是可重建索引。
3. PDF、markdown、json、图片、表格等大对象存文件系统；SQLite 只存 object metadata 和路径 key。
4. `sha256` 是对象完整性和文件级去重字段，不是 paper id。
5. embedding 走外部 API provider，本地不要求 GPU。
