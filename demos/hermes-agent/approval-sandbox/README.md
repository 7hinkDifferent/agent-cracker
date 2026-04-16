# Hermes Agent — approval-sandbox

## 目标

用最简代码复现 Hermes 的安全执行模型：**危险命令检测 + 审批状态 + 受控执行后端**。

## 原理

Hermes 不会把 terminal / execute_code 当成完全裸露的能力。它先用 `DANGEROUS_PATTERNS` 检查命令是否属于高风险操作（递归删除、SQL DROP、远程脚本直通 shell、硬重置等），再决定是直接执行、请求审批，还是继续阻断。

这种设计非常适合平台型 agent：无论入口是 CLI、gateway、cron 还是 ACP，只要最终会落到执行后端，就必须先过同一套审批门槛。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/approval-sandbox/
├── README.md
├── approval_sandbox.py
└── main.py
```

## 关键代码解读

```python
def execute(self, command: str) -> str:
    dangerous, description = detect_dangerous_command(command)
    if dangerous and description and not self.approvals.is_approved(description):
        return f"BLOCKED pending approval: {description}"
    return self.run_command(command)
```

这正是 Hermes 的安全边界：**先判定风险，再决定能否进入执行后端**。模型可以提出命令，但真正执行之前还要过审批层。

## 与原实现的差异

- 原版 pattern 列表更长，包含系统路径、gateway 自杀命令、shell `-c`、敏感文件写入等；demo 只保留最典型的 4 类模式
- 原版有 per-session / permanent allowlist / gateway async approval；demo 只保留一个内存审批集合
- 原版会与真实 terminal backend、execute_code sandbox 联动；demo 用 `fake_backend()` 简化

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `tools/approval.py`, `tools/terminal_tool.py`, `tools/code_execution_tool.py`
