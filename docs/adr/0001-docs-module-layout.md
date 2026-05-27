# ADR-0001：按模块重组 docs 结构

## 状态

Proposed

## 背景

早期文档集中放在 `docs/api/` 下，例如 searcher 的 AI context、API、provider contract、status 和 quick decision table。随着 search、storage、rag 等核心模块加入，继续平铺会导致：

- 文件命名互相抢占。
- search 文档和 storage 文档混在一起。
- 未来代码智能体难以判断应阅读哪个模块。
- API、schema、配置、状态文档边界不清。

## 决策

将 docs 重组为：

```text
docs/
  API_INDEX.md
  architecture/
  modules/<module>/
  templates/
  adr/
  api/                 # 仅兼容旧路径
```

每个核心模块拥有自己的文档命名空间。非核心 workflow 或应用层能力可以放入对应核心模块文档，或保留过渡说明，但不应默认成为新的顶层模块。

## 影响

- 新核心模块必须先更新 `docs/architecture/MODULE_BOUNDARIES.md`，再在 `docs/modules/<module>/` 下新增文档。
- `docs/api/` 不再新增正文文档。
- 旧路径可以保留 README 或跳转说明，避免已有引用完全断裂。
- `docs/API_INDEX.md` 成为唯一总入口。
