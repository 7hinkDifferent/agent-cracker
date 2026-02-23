# Demo: Pi-Agent — Mini-Pi

## 目标

串联 4 个 MVP 组件，构建最小完整 coding agent。

## 串联角色

Mini-Pi 不引入新代码——它**仅通过 import 组合**已有的 MVP demo 模块，验证组件间的接口兼容性和协作流程。

## 组件组合

```
mini-pi/main.py
    ├── import builder     ← prompt-builder/builder.py    (Prompt 组装)
    ├── import providers   ← llm-multi-provider/providers.py (LLM 调用)
    ├── import loop        ← agent-session-loop/loop.py     (会话循环)
    └── import tools       ← pluggable-ops/tools.py          (执行环境)
```

**工作流**：
1. `LocalOps` 创建执行环境（文件读写 + shell 命令）
2. `PromptBuilder` 组装 system prompt（角色 + 工具 + 指南 + 上下文）
3. `SessionLoop` 驱动双层循环（LLM → tool call → 结果回填）
4. 工具通过 `LocalOps` 执行实际操作（read/edit/bash）

## 运行

```bash
cd demos/pi-agent/mini-pi

# Mock 模式（无需 API key）
uv run python main.py --mock

# Live 模式（需要 API key）
export OPENAI_API_KEY=sk-xxx
uv run --with litellm python main.py

# 指定模型
DEMO_MODEL=claude-sonnet-4-20250514 uv run --with litellm python main.py
```

## 文件结构

```
demos/pi-agent/mini-pi/
├── README.md       # 本文件
└── main.py         # 串联入口（仅 import，不引入新逻辑）
```

## 关键代码解读

### 组件导入（sys.path 注入）

```python
_DEMO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _subdir in ("prompt-builder", "llm-multi-provider", "agent-session-loop", "pluggable-ops"):
    sys.path.insert(0, os.path.join(_DEMO_DIR, _subdir))

from builder import PromptBuilder, TOOL_READ, TOOL_EDIT, TOOL_BASH
from providers import LlmClient, detect_provider
from loop import SessionLoop, EventStream, MessageQueue, Message
from tools import LocalOps
```

### 工具 ↔ Ops 桥接

```python
def make_tools(ops, cwd):
    def read_file(args):
        return ops.read_file(os.path.join(cwd, args["path"]))

    def edit_file(args):
        content = ops.read_file(path)
        ops.write_file(path, content.replace(search, replace))

    def run_bash(args):
        _, output = ops.run_command(args["command"], cwd)
        return output
```

### LLM 桥接

```python
class LlmBridge:
    """将 SessionLoop 的 Message 接口连接到 LlmClient。"""
    async def complete(self, messages):
        llm_messages = [LlmMessage(...) for msg in messages]
        response = self.client.complete(model, llm_messages, tool_schemas)
        return Message(role="assistant", content=response.content, ...)
```

## 与原实现的差异

| 方面 | 原实现 | Mini-Pi |
|------|--------|---------|
| 组件耦合 | 单体包内直接引用 | sys.path 跨目录 import |
| LLM 调用 | 流式 streaming | 同步调用 |
| 错误恢复 | 完整 retry + fallback | 无 |
| 用户交互 | REPL + TUI | 单次执行 |
| 扩展系统 | 钩子 + 插件注册 | 无 |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 基于 commit: `316c2af`
