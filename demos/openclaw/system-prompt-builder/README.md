# OpenClaw — System Prompt Builder

复现 OpenClaw 的 14+ sections 动态 prompt 组装引擎（Dimension 4: Prompt 工程）。

## 机制说明

OpenClaw 完全重写了 pi-agent 的 system prompt 构建器，支持 3 种模式和 13+ 个条件注入段落。

### 3 种 Prompt 模式

| 模式 | 用途 | Sections |
|------|------|----------|
| `full` | 主 agent | 全部 13+ |
| `minimal` | 子 agent | 仅 Identity + Tooling + Safety + Runtime |
| `none` | 纯身份 | 一行身份声明 |

### 组装流程

```
Identity → Tooling → Tool Call Style → Safety
  → Skills（匹配时注入）
  → Memory（启用时注入）
  → Sandbox（容器时注入）
  → Date & Time → Workspace
  → Project Context（SOUL.md 人格注入）
  → Messaging（通道指令）
  → Silent Reply
  → Runtime 元数据
```

### 关键特性

- **Skills 注入**: 按用户消息匹配 SKILL.md，每轮最多注入 1 个
- **SOUL.md 人格**: 检测上下文文件中的 SOUL.md，注入人格指引
- **Sandbox 描述**: Docker 容器路径映射、browser bridge 状态
- **Runtime 元数据**: agent/host/os/model/channel/capabilities 一行式注入

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/agents/system-prompt.ts` | 主构建器（696 行） |
| `src/agents/system-prompt-params.ts` | 参数解析 |
| `src/agents/pi-embedded-runner/system-prompt.ts` | 内嵌运行器覆盖 |

## 运行

```bash
uv run python main.py
```

## 关键简化

| 原始实现 | Demo 简化 |
|---------|----------|
| 14+ sections | 保留 13 个核心段落 |
| Authorized Senders (SHA256) | 省略 |
| Documentation 路径注入 | 省略 |
| Plugin hooks (before_prompt_build) | 省略 |
| CLI Quick Reference | 省略 |
