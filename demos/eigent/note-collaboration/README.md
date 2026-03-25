# Demo: eigent — note-collaboration

## 目标

用最简代码复现 eigent 的 **跨 Agent 笔记协作机制** — NoteTakingToolkit 的 CRUD 操作 + shared_files 注册表让多个 Agent 在同一任务中共享笔记。

## 平台角色

**协作记忆层**（D10）— 笔记是 eigent 多 Agent 协作的核心信息交换机制。不同于 Agent 之间的直接消息传递，笔记提供了持久化的共享知识空间。Browser Agent 记录调研结果，Developer Agent 读取后创建实现计划，Document Agent 汇总生成报告 — 全程通过 shared_files 约定互相发现。

## 原理

Eigent 的笔记协作分两层：

1. **NoteTakingToolkit**（`note_taking_toolkit.py`）：提供 4 个工具方法 — `list_note()` 列出所有笔记、`read_note(filename)` 读取内容、`create_note(filename, content)` 创建笔记、`append_note(filename, content)` 追加内容。每个 Agent 拥有独立的 Toolkit 实例，但共享同一个底层存储
2. **shared_files 约定**：Agent 创建文件后注册到 `shared_files` 字典（agent_name → filenames），其他 Agent 通过查询 shared_files 发现可用文件。这是一种约定优于配置的协作模式

关键设计：笔记按任务隔离（每个任务独立的存储空间），但任务内的所有 Agent 共享读写权限。

## 运行

```bash
cd demos/eigent/note-collaboration
uv run python main.py
```

无需 API key — 此 demo 不调用 LLM，完全模拟多 Agent 笔记协作流程。

## 文件结构

```
demos/eigent/note-collaboration/
├── README.md           # 本文件
└── main.py             # NoteStorage/SharedFiles/NoteTakingToolkit + 3 Agent 协作演示
```

## 关键代码解读

### NoteTakingToolkit.create_note() — 创建 + 注册

```python
def create_note(self, filename, content):
    self._storage.create(filename, content, self.agent_name)
    self._shared_files.register(self.agent_name, filename)  # 关键：让其他 Agent 可发现
```

### SharedFiles — 跨 Agent 文件发现

```python
class SharedFiles:
    _registry: dict[str, list[str]]  # agent_name -> [filenames]

    def register(self, agent_name, filename): ...
    def get_by_agent(self, agent_name) -> list[str]: ...
    def all_files(self) -> list[str]: ...
```

### 协作流程

```
browser_agent  → create_note("research.md")      → shared_files 注册
developer_agent → read_note("research.md")        → 读取调研结果
developer_agent → create_note("implementation.md") → shared_files 注册
document_agent  → list_note() + read_note()        → 汇总所有笔记
document_agent  → create_note("summary.md")        → shared_files 注册
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 存储 | 任务工作目录的文件系统 | 内存 dict |
| 文件格式 | 实际 Markdown/文本文件 | 字符串内容 |
| shared_files | ContextVar + 任务级上下文 | 显式传入的共享对象 |
| 权限控制 | 基于任务隔离 | 所有 Agent 完全共享 |
| @listen_toolkit | 自动织入 UI 事件 | 无事件织入 |
| 并发安全 | asyncio.Lock | 无（单线程模拟） |

**保留的核心**：NoteTakingToolkit 的 4 个方法（list/read/create/append）、shared_files 注册约定、多 Agent 共享存储、按任务隔离的存储空间。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/agent/toolkit/note_taking_toolkit.py`
