# Error Handling & Recovery

复现 Gemini CLI 的错误处理与恢复机制。

## 原理

Gemini CLI 对不同类型的错误有不同处理策略：

```
LLM 错误类型                          工具错误类型
├─ ContextWindowWillOverflow    ├─ STOP_EXECUTION → 正常结束
├─ InvalidStream                ├─ FATAL_ERROR → 终止循环
├─ Error                         ├─ INVALID_PARAMS → 继续循环
└─ (LLM 可恢复)                  ├─ TOOL_NOT_FOUND → 重试
                                 └─ (Tool 失败)
```

## 关键特性

1. **错误分类**：ToolErrorType enum 区分可恢复/致命错误
2. **差异化处理**：不同错误走不同路径
3. **致命错误检测**：isFatalToolError() 判定是否中止
4. **错误事件**：每个错误都作为事件记录

## 运行方式

```bash
uv run main.py
```

## 对应源码

- [packages/core/src/tools/tool-error.ts](../../../projects/gemini-cli/packages/core/src/tools/tool-error.ts)
- [packages/core/src/agent/legacy-agent-session.ts](../../../projects/gemini-cli/packages/core/src/agent/legacy-agent-session.ts) (L174-200, 错误处理 switch 块)
