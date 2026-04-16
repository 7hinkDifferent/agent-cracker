# Hermes Agent — prompt-assembly

## 目标

用最简代码复现 Hermes 的 system prompt 分层组装：**stable cached prompt** 与 **ephemeral overlay** 分离。

## MVP 角色

这是 Hermes MVP 中的**Prompt 组装层**。主循环会缓存这部分结果，tool、memory、skills、context files 和平台 hints 都在这里被汇入。

## 原理

Hermes 不把所有动态信息都直接塞进同一个 system prompt。它会把相对稳定的内容——例如 agent identity、`MEMORY.md`、`USER.md`、skills index、context files、platform hints——拼成 cached prompt；而 session id、当前入口、临时运行约束等易变化信息则放到 ephemeral overlay 中。

这种设计的直接好处是提高前缀缓存命中率。mid-session 新增 memory、gateway overlay 或临时执行约束时，不必把整段系统提示全部重建，也不容易污染长期会话的一致性。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/prompt-assembly/
├── README.md
├── main.py
├── prompt_builder_demo.py
└── sample_context/
    ├── .hermes.md
    └── AGENTS.md
```

## 关键代码解读

```python
cached = assembler.build_cached_prompt(inputs)
ephemeral = assembler.build_ephemeral_overlay(inputs)
```

`build_cached_prompt()` 会按 Hermes 的优先级装入：
1. agent identity
2. user system message
3. `MEMORY.md` / `USER.md`
4. skills index
5. `.hermes.md` / `AGENTS.md` 等 context files
6. platform hint

而 `build_ephemeral_overlay()` 只装会频繁变化的 session metadata。

## 与原实现的差异

- 原版会扫描更完整的文件优先级链，并带有 prompt injection 保护；demo 只保留最核心的文件发现顺序
- 原版还包含 model-family 特定约束（GPT/Gemini/Codex 等）；demo 只保留平台提示
- 原版会结合外部 memory provider 与更多 runtime metadata；demo 只保留最关键的 cached/ephemeral 切分

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `agent/prompt_builder.py`, `run_agent.py`
