# {{AGENT_NAME}} — Deep Dive Analysis

> Auto-generated from template on {{DATE}}
> Repo: {{REPO_URL}}
> Analyzed at commit: [`{{COMMIT_SHORT}}`]({{REPO_URL}}/tree/{{COMMIT_SHA}}) ({{COMMIT_DATE}})

## 1. Overview & Architecture

### 项目定位
<!-- 一句话描述这个 agent 是什么、解决什么问题 -->

### 技术栈
<!-- 语言、框架、关键依赖 -->

### 核心架构图
<!-- ASCII 或 Mermaid 图 -->

```
[User Input] -> [???] -> [LLM] -> [???] -> [Output]
```

### 关键文件/目录
| 文件/目录 | 作用 |
|-----------|------|
| | |

---

## 2. Agent Loop（主循环机制）

### 循环流程
<!-- 描述 agent 的主事件循环：输入 -> 思考 -> 行动 -> 观察 -> ... -->

### 终止条件
<!-- 什么时候停止循环？ -->

### 关键代码
```
# 粘贴核心循环代码片段
```

---

## 3. Tool/Action 系统

### Tool 注册机制
<!-- 如何定义和注册 tool？ -->

### Tool 列表
| Tool | 功能 | 实现方式 |
|------|------|----------|
| | | |

### Tool 调用流程
<!-- LLM 如何选择和调用 tool？ -->

---

## 4. Prompt 工程

### System Prompt 结构
<!-- system prompt 的组成部分 -->

### 动态 Prompt 组装
<!-- 哪些部分是动态生成的？ -->

### Prompt 模板位置
<!-- 文件路径 -->

---

## 5. 上下文管理

### 上下文窗口策略
<!-- 如何管理有限的 context window？ -->

### 文件/代码的 context 策略
<!-- 如何决定哪些文件/代码片段放入 context？ -->

### 对话历史管理
<!-- 如何截断/压缩历史？ -->

---

## 6. 错误处理与恢复

### LLM 输出解析错误
<!-- 如何处理 LLM 返回的非预期格式？ -->

### Tool 执行失败
<!-- tool 出错后如何恢复？ -->

### 重试机制
<!-- 有无自动重试？策略是什么？ -->

---

## 7. 关键创新点

### 独特设计
<!-- 这个 agent 有什么与众不同的设计？ -->

### 值得借鉴的模式
<!-- 可以复用到其他 agent 的 pattern -->

---

## 8. 跨 Agent 对比

### vs 其他 agent
| 维度 | {{AGENT_NAME}} | 对比 Agent |
|------|----------------|------------|
| Agent Loop | | |
| Tool 系统 | | |
| Context 策略 | | |
| 错误处理 | | |

### 总结
<!-- 一段话总结这个 agent 的核心特点和适用场景 -->
