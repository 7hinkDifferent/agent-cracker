# Demo: eigent — mini-eigent

## 目标

串联所有 MVP 组件 + 平台机制，构建最小完整 agent，复现 eigent 的**完整消息流路径**：通道接入 → 复杂度路由 → Workforce 编排 → Agent 执行 → SSE 响应。

## 原理

Mini-Eigent 通过 `import` 兄弟 demo 的模块来串联所有机制，自身只实现核心编排逻辑（`MiniEigent.handle_message()`）：

```
消息到达 (CLI/Webhook)
  → 复杂度路由 (complexity-router)
  → 简单: 直接回答 + SSE wait_confirm
  → 复杂: Workforce 编排
    → Prompt 组装 (prompt-assembly) 为每个 Agent 构建 system prompt
    → Toolkit 分发 (toolkit-dispatch) 按 Agent 类型收集工具
    → 并行执行 3 个 Agent (browser + developer + document)
    → 笔记协作 (note-collaboration) Agent 间共享结果
    → SSE 流式 (sse-streaming) 推送事件: confirmed → activate → deactivate → end
```

## 运行

```bash
cd demos/eigent/mini-eigent
uv run python main.py
```

无需 API key — 所有 LLM 调用已模拟。

## 文件结构

```
demos/eigent/mini-eigent/
├── README.md           # 本文件
└── main.py             # MiniEigent 类（import 兄弟 demo 模块）
```

## 导入的兄弟模块

| 模块来源 | 导入内容 | 用途 |
|----------|----------|------|
| queue-event-loop | Action, ActionData, TaskLock, sse_json | 队列 + SSE 格式 |
| prompt-assembly | AgentType, PromptContext, assemble_prompt | 动态 prompt 构建 |
| toolkit-dispatch | TerminalToolkit, get_toolkits, listen_toolkit | 工具收集 + 事件 |
| sse-streaming | (间接通过 sse_json) | SSE 事件格式 |
| note-collaboration | (内联简化) | 笔记协作 |
| complexity-router | (内联简化) | 复杂度判断 |

## 关键代码解读

```python
class MiniEigent:
    async def handle_message(self, question, source="cli"):
        # 1. 复杂度路由
        is_complex = self._check_complexity(question)
        if not is_complex:
            self._emit_sse("wait_confirm", {"content": answer})
            return

        # 2. Workforce 编排
        self._emit_sse("confirmed", {"question": question})
        for subtask in subtasks:
            # 3. 每个 Agent: 组装 Prompt + 收集 Toolkit + 执行
            prompt = self._assemble_prompt(subtask["agent"])
            tools = self._collect_tools(subtask["agent"])
            result = self._simulate_agent_work(subtask["agent"], subtask["task"])
            # 4. 笔记协作
            self.notes[f"{agent}_findings"] = result

        # 5. SSE 完成事件
        self._emit_sse("end", {"result": final_result})
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| Agent 执行 | CAMEL ChatAgent + LLM | 模拟字符串返回 |
| 并行 | CAMEL TaskChannel 线程池 | 串行模拟 |
| SSE 传输 | FastAPI StreamingResponse | 收集到列表 |
| Trigger | Celery Beat + Webhook HTTP | source 参数标记 |
| 笔记 | 文件系统 NoteTakingToolkit | dict 存储 |

**保留的核心**：完整消息流路径、复杂度分流、多 Agent 协作编排、SSE 事件生命周期、笔记协作约定。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/service/chat_service.py`
