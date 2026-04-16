# Hermes Agent — tool-registry-discovery

## 目标

用最简代码复现 Hermes 的 **AST 扫描 + 自注册 registry + toolset 过滤** 机制。

## MVP 角色

这是 Hermes MVP 中的**工具发现与分发层**。主循环依赖它得到可见工具列表，并在 tool call 返回后统一 dispatch。

## 原理

Hermes 并不手写一份巨大的工具字典，而是让每个 `tools/*.py` 在模块顶层调用 `registry.register(...)`。随后 `discover_builtin_tools()` 通过 AST 先扫描哪些文件确实包含顶层注册语句，只导入这些模块；避免把 helper、测试或半成品模块误当成工具。

接着，agent 再基于当前入口启用的 toolsets（例如 CLI、gateway、ACP、cron）过滤掉不该暴露给模型的工具。这样 builtin tool、plugin tool、MCP tool 都能走同一套注册与过滤流程。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/tool-registry-discovery/
├── README.md
├── main.py
├── tool_registry.py
└── sample_tools/
    ├── helper_only.py
    ├── memory_tool.py
    ├── read_file_tool.py
    └── terminal_tool.py
```

## 关键代码解读

```python
def module_registers_tools(module_path: Path) -> bool:
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    return any(_is_registry_register_call(stmt) for stmt in tree.body)


def discover_builtin_tools(tools_dir: Path) -> list[str]:
    for module_path in sorted(tools_dir.glob("*.py")):
        if module_registers_tools(module_path):
            import_module(module_path)
```

Hermes 先 AST 扫描、再 import。这样做的重点不是“快”，而是**只导入真正会注册工具的模块**，避免副作用扩散。

## 与原实现的差异

- 原版 registry 还支持 MCP 动态刷新、toolset alias、availability checks；demo 只保留 builtin discovery 主干
- 原版 dispatch 会处理 async tool；demo 统一成同步 handler
- 原版 `model_tools.py` 还会拼接 schema 给模型；这里仅演示 discovery 与 dispatch

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `tools/registry.py`, `model_tools.py`
