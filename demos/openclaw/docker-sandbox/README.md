# OpenClaw — Docker Sandbox

复现 OpenClaw 的 Docker 容器沙箱隔离机制（Dimension 11: 安全模型与自治）。

## 机制说明

OpenClaw 通过 Docker 容器为 Agent 提供安全隔离的执行环境。

```
Host Workspace ─── mount ──→ /agent/workspace (容器内)
                              │
Container ───────────────────│── exec tool（沙箱内执行）
                              │── read/write/edit（通过 bridge 访问）
                              └── elevated exec（需审批 or auto-approve）
```

### 核心特性

| 特性 | 说明 |
|------|------|
| Config Hash | 配置变更自动检测并重建容器 |
| 热容器窗口 | 5 分钟内复用已有容器 |
| 安全基线 | `--cap-drop ALL`, `--no-new-privileges` |
| Mount 校验 | 禁止路径遍历 (`..`) 和危险目录 (`/etc`, `/root`) |
| Elevated Exec | 危险操作按策略审批 (ask / auto-approve) |
| Workspace Access | 4 级权限 (none / read / write / admin) |

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/agents/sandbox/docker.ts` | 容器生命周期管理 |
| `src/agents/sandbox/validate-sandbox-security.ts` | 安全校验 |

## 运行

```bash
uv run python main.py
```

## 关键简化

| 原始实现 | Demo 简化 |
|---------|----------|
| 真实 Docker API 调用 | 模拟容器操作 |
| Browser bridge 容器 | 省略 |
| NoVNC 观察模式 | 省略 |
| Agent/Workspace 级 scope | 简化为单一 scope |
