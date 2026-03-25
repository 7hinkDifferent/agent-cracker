# Context Window Management

## 目标

复现 Gemini CLI 的大上下文窗口管理机制，在 1M token 容量下动态优化文件选择、历史管理和溢出检测。

## 原理

Gemini CLI 利用 Gemini 的大上下文窗口（1M token）但仍需谨慎管理：

1. **动态窗口检测**：
   - LLM 返回 `ContextWindowWillOverflow` 事件时，agent 立即停止并报告上下文已满
   - Genai SDK 内部维护计数，client 端可监听溢出事件

2. **增量式上下文构建**：
   ```
   初始化 → [User Query] → [File Context] → [Tool Results] → ...
                ↓
           估算 token 数
                ↓
           Token 数 < Limit? 
           ├─ Yes → 继续添加   
           └─ No → 触发溢出事件
   ```

3. **Just-In-Time (JIT) 文件加载**：
   - 不预加载全部项目文件，而是按需动态加载
   - LLM 通过 `glob`、`grep` 搜索工具表达需求
   - 工具返回文件路径 → agent 要求用户选择 → 加载到上下文

4. **智能文件选择**：
   - **显式选择**：用户或 LLM 指定的文件
   - **隐式选择**：编辑工具返回的 diffs 自动包含编辑过的文件
   - **历史追踪**：已加载过的文件不必重复加载

5. **历史压缩与修剪**：
   - **事件滑动窗口**：只保留最近 N 个事件的完整信息，更早的事件只作为摘要
   - **聊天记录摘要**：而非逐字保留，生成高级摘要（LLM 可参考但不占用太多 token）
   - **标志位管理**：通过 `eventId` 支持游标，快速定位特定时间点

## 运行

```bash
cd demos/gemini-cli/context-window-management/
uv run --with pydantic main.py
```

## 文件结构

```
context-window-management/
├── README.md          # 本文件
└── main.py            # 上下文窗口管理实现 (~400 行)
```

## 关键代码解读

### 1. Token 计数与预估
```python
class TokenEstimator:
    """估算不同输入的 token 数"""
    
    def estimate_tokens(self, text: str) -> int:
        "粗略估算（实际使用 Gemini API 的 countTokens API）"
        return len(text) // 4  # 平均 4 chars/token
    
    def get_context_usage(self) -> float:
        "返回当前 token 使用率 (0.0 - 1.0)"
        return self.current_tokens / self.max_tokens
```

### 2. JIT 文件加载
```python
class JITContextManager:
    """Just-In-Time 文件和数据加载"""
    
    async def load_files_for_query(self, query: str):
        # 分析 query，提取文件路径或模式
        # 执行 glob/grep 搜索
        # 返回搜索结果，等待用户选择
        # 加载用户选中的文件
```

### 3. 溢出检测与处理
```python
async def on_context_will_overflow(event: OverflowEvent):
    """
    接收溢出事件时的处理：
    1. 立即保存当前状态（eventId）
    2. 停止接收新输入
    3. 提示用户"上下文将满"
    4. 支持用户选择：继续（可能失败）或开新会话
    """
```

## 与原实现的差异

| 特性 | 原实现 | Demo |
|------|--------|------|
| Token 计数 | Genai SDK 内置 API | 简单字符计数估算 |
| 窗口大小 | 1M token（Gemini Pro） | 模拟 10K token（缩小版） |
| JIT 加载 | `jit-context.ts` + 文件系统 API | 内存中模拟文件和搜索结果 |
| 历史模型 | EventHistory + eventId/streamId | 简化的事件队列 + 游标 |
| 摘要策略 | 多级摘要（事件摘要 + 聊天摘要） | 单层摘要（完整事件日志） |

## 相关文档

- 基于 commit: [`0c91985`](https://github.com/google-gemini/gemini-cli/tree/0c919857fa5770ad06bd5d67913249cd0f3c4f06)
- 核心源码: `packages/core/src/agent/agent-session.ts` (stream/replay), `packages/core/src/jit-context.ts`
- 相关维度: D5（上下文管理）
- 参考 Demo: [event-driven-loop](../event-driven-loop/) (D2), [session-replay](../session-replay/) (D5)
