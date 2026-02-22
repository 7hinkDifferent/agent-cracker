# Demo: Pi-Agent — Pluggable Operations 可插拔操作层

## 目标

用最简代码复现 pi-agent 的 Pluggable Operations 模式：通过依赖注入，让同一 tool 代码透明切换执行环境。

## 原理

Pi-agent 中每个 tool（read, bash, write, edit）的底层操作都通过接口注入，而非硬编码本地文件系统：

```typescript
// 原实现：只需替换 operations 即可切换环境
const readTool = createReadTool(cwd, { operations: sshReadOps });
const bashTool = createBashTool(cwd, { operations: sshBashOps });
```

这样同一套 tool 可以透明地在本地、SSH 远程、Docker 容器等环境中运行，tool 的业务逻辑完全不变。

核心模式：
1. **Protocol 定义接口**：`FileOperations`（read_file, write_file）、`ShellOperations`（run_command）
2. **默认实现**：`LocalOps` 用本地 I/O
3. **工厂注入**：`create_read_tool(cwd, operations=None)` — `None` 时用默认本地实现

## 运行

```bash
cd demos/pi-agent/pluggable-ops
python main.py
```

无外部依赖。本地环境执行真实 I/O，SSH/Docker 环境为模拟输出。

## 文件结构

```
demos/pi-agent/pluggable-ops/
├── README.md       # 本文件
├── main.py         # 演示：同一 tool 在 3 种环境运行
└── tools.py        # Tool 工厂 + Operations Protocol + 3 种实现
```

## 关键代码解读

### Operations Protocol

```python
class FileOperations(Protocol):
    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> None: ...
    def file_exists(self, path: str) -> bool: ...

class ShellOperations(Protocol):
    def run_command(self, command: str, cwd: str) -> tuple[int, str]: ...
```

### Tool 工厂

```python
def create_read_tool(cwd, operations=None):
    ops = operations or LocalOps()  # 默认本地

    def read_file(path):
        content = ops.read_file(abs_path)  # 调用注入的实现
        return {"content": content, "lines": len(lines)}

    return {"name": "read", "execute": read_file}
```

### 环境切换

```python
# 本地
read = create_read_tool(cwd)                                # LocalOps
# SSH
read = create_read_tool(cwd, operations=MockSSHOps("host")) # SSH 实现
# Docker
read = create_read_tool(cwd, operations=MockDockerOps())     # Docker 实现
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 语言 | TypeScript interface | Python Protocol |
| Tool 数量 | 7 个（read, bash, edit, write, grep, find, ls） | 2 个（read, bash） |
| Schema 校验 | TypeBox/AJV 参数校验 | 无 |
| 流式回调 | onUpdate callback | 无 |
| AbortSignal | 支持取消 | 无 |
| 远程实现 | 真实 SSH/Docker 操作 | 打印模拟 |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 核心源码: `packages/coding-agent/src/core/tools/` (read.ts, bash.ts, write.ts)
