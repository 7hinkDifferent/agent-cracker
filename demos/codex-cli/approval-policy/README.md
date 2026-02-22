# Demo: Codex CLI — 三级审批策略（Approval Policy）

## 目标

用最简代码复现 Codex CLI 的核心安全机制：三级审批策略 + 危险命令检测。

## 原理

Codex CLI 的安全模型核心是**渐进式信任**——通过 `AskForApproval`（审批策略）× `SandboxPolicy`（沙箱策略）的组合，决定每个命令是否需要用户确认。

决策流程：
1. **命令解析**：用 shlex 将命令拆分为 token 数组
2. **禁止前缀匹配**：检查命令是否匹配 50+ 个危险前缀（解释器、提权、包管理器等）→ 直接 Forbidden
3. **安全命令检测**：检查是否为已知无副作用命令（ls, cat, grep...）→ 可能直接 Allow
4. **策略组合评估**：根据 `approval_mode × sandbox_policy` 决定最终结果

三级审批策略：

| 模式 | 文件读取 | 文件写入 | Shell 执行 | 说明 |
|------|---------|---------|-----------|------|
| **Suggest** | 自由 | 需审批 | 需审批 | 最保守，每步确认 |
| **Auto-Edit** | 自由 | 自动 | 需审批 | 文件编辑免审批 |
| **Full-Auto** | 自由 | 自动 | 自动 | 依赖沙箱兜底 |

## 运行

```bash
cd demos/codex-cli/approval-policy
uv run python main.py
```

## 文件结构

```
demos/codex-cli/approval-policy/
├── README.md      # 本文件
├── policy.py      # 审批策略引擎（枚举 + 前缀匹配 + 评估逻辑）
└── main.py        # 演示：多种命令 × 多种策略组合的审批决策
```

## 关键代码解读

### 禁止前缀匹配

```python
BANNED_PREFIXES = [
    ["python3"], ["python3", "-c"],   # 解释器
    ["bash"], ["bash", "-c"],          # Shell
    ["sudo"],                          # 提权
    ["node"], ["node", "-e"],          # JS 运行时
    ["rm", "-rf"],                     # 危险删除
    ...
]

def is_banned_prefix(tokens):
    for prefix in BANNED_PREFIXES:
        if tokens[:len(prefix)] == prefix:
            return True
```

### 评估决策

```python
def evaluate(cmd, approval_mode, sandbox_policy) -> EvalResult:
    # 1. 禁止前缀 → Forbidden（无论什么策略都拦截）
    # 2. 安全命令 + 非 Suggest → Allow
    # 3. Full-Auto + 有沙箱 → Allow（沙箱兜底）
    # 4. Full-Auto + 无沙箱 → NeedsApproval（无保护不放行）
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 语言 | Rust（exec_policy.rs） | Python |
| 禁止前缀 | 89 个前缀 | 精选 30+ 个代表性前缀 |
| 规则引擎 | ExecPolicy 规则文件加载 + 正则匹配 | 无，仅前缀匹配 |
| Amendment | 用户可添加临时放行规则 + 缓存 | 无 |
| Bash 内嵌 | 解析 `bash -lc "..."` 提取内部命令 | 无 |

## 相关文档

- 分析文档: [docs/codex-cli.md](../../../docs/codex-cli.md)
- 原项目: https://github.com/openai/codex
- 核心源码: `codex-rs/core/src/exec_policy.rs`
