# <Module Name> 文档模板

每个新模块至少建立：

```text
docs/modules/<module>/
  AI_CONTEXT.md
  STATUS.md
```

稳定对外开放后再补充：

```text
API.md
QUICK_DECISION_TABLE.md
CONFIGURATION.md        # 如果有配置
SCHEMA.md               # 如果有数据库 schema
PROVIDER_CONTRACT.md    # 如果支持第三方 provider
```

## AI_CONTEXT.md 应包含

- 模块一句话职责。
- 当前已实现。
- 当前未实现。
- 稳定入口。
- 典型调用链。
- 与其他模块关系。
- 禁止事项。

## STATUS.md 应包含

- 已实现。
- 未实现。
- 第一阶段目标。
- 暂不做的内容。
- 风险点。

## API.md 应包含

- 稳定 facade。
- 输入输出。
- 返回类型。
- 外部不应调用的内部类。
- 常见调用示例。

## QUICK_DECISION_TABLE.md 应包含

以“我想……”开头的任务导向条目，方便未来对话快速定位正确模块和入口。
