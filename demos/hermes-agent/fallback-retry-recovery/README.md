# Hermes Agent — fallback-retry-recovery

## 目标

用最简代码复现 Hermes 的恢复链：**tool name / JSON 自修复 + provider fallback + credential pool 轮换**。

## 原理

Hermes 对坏输出和 provider 失败的容忍度很高。模型若返回了错误的 tool 名，Hermes 会尝试根据可用工具表做修复；如果 tool arguments JSON 损坏，会先做修复或重试；如果 provider 不可用，则沿 fallback 链继续尝试，并在同一 provider 下轮换 credential pool。

这种恢复链让 Hermes 更适合长期运行：它不会因为一次格式错误或单个 API key 挂掉就直接崩溃。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/fallback-retry-recovery/
├── README.md
├── main.py
└── recovery.py
```

## 关键代码解读

```python
for attempt in attempts:
    key = pool.next_key(attempt.name)
    if attempt.fail:
        errors.append(...)
        continue
    return ...
```

Hermes 的思路不是只依赖一个 provider 或一个 key，而是把**格式修复、provider fallback、credential rotation** 组合成连续的恢复链。

## 与原实现的差异

- 原版重试还会考虑 streaming / non-streaming 切换、指数退避和中断安全；demo 只保留最核心的恢复分层
- 原版 tool repair 会结合更多上下文和 tool 可见性；demo 只处理 `-` → `_` 这种常见修复
- 原版 JSON 修复更复杂；demo 只演示一个最小可见案例

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `run_agent.py`
