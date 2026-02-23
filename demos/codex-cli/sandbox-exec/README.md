# sandbox-exec — 平台沙箱执行

复现 Codex CLI 的平台沙箱执行机制：macOS Seatbelt 策略生成、Linux Landlock 规则、多层防御管线。

> Based on commit: [`0a0caa9`](https://github.com/openai/codex/tree/0a0caa9df266ebc124d524ee6ad23ee6513fe501) (2026-02-23)

## 运行

```bash
uv run python main.py
```

## Demo 内容

| Demo | 说明 |
|------|------|
| Seatbelt Policy | macOS sandbox-exec S-expression 策略生成 |
| Landlock Rules | Linux Landlock 路径权限规则生成 |
| Banned Commands | 36+ 禁止命令前缀检测 |
| Defense Pipeline | 5 层防御管线（banned→approval→network→sandbox→exec） |
| Platform Comparison | Seatbelt vs Landlock vs Windows 沙箱对比 |

## 核心机制

```
用户命令
  ↓
┌─ 1. 禁止命令检测 ────────────────────┐
│  36+ 前缀匹配（python3、bash、sudo...）│
└──────────────────────────────────────┘
  ↓ pass
┌─ 2. 审批策略 ────────────────────────┐
│  safe prefix → auto-approve          │
│  其他 → 用户审批 / 模式决定          │
└──────────────────────────────────────┘
  ↓ approved
┌─ 3. 网络策略 ────────────────────────┐
│  curl/wget/git clone → 检查网络权限  │
└──────────────────────────────────────┘
  ↓ pass
┌─ 4. Seatbelt/Landlock 策略生成 ──────┐
│  macOS: (deny default) + allow list  │
│  Linux: landlock_add_rule per path   │
└──────────────────────────────────────┘
  ↓ policy
┌─ 5. 沙箱执行 ────────────────────────┐
│  sandbox-exec -p 'policy' /bin/sh -c │
└──────────────────────────────────────┘
```

## 核心源码

| 机制 | 原始文件 |
|------|----------|
| Seatbelt 策略生成 | `codex-rs/core/src/seatbelt.rs` |
| 命令执行 + 沙箱包装 | `codex-rs/core/src/exec.rs` |
| 禁止命令前缀 | `codex-rs/core/src/exec.rs` → `BANNED_PREFIX_SUGGESTIONS` |

## 与原实现的差异

- **不实际调用 sandbox-exec**: 生成策略字符串但不执行（避免系统依赖）
- **Landlock 为规则生成**: 不调用 Linux 系统调用（prctl/landlock_restrict_self）
- **禁止前缀 36 项**: 原实现 50+ 项，demo 覆盖核心类别
