# 拆解 3 个开源 Coding Agent，我发现了它们的核心秘密

> 我花了两周读了 aider、codex-cli、pi-agent 的源码，把每个 agent 的核心机制用 100-200 行代码复现。这篇文章分享三个最让我意外的发现。

## 发现一：Aider 用 PageRank 理解你的代码库

大多数人以为 Coding Agent 就是把文件塞进 context window。但 aider 做了一件聪明得多的事——它用 **tree-sitter 解析整个代码库的 AST，构建引用关系图，然后跑 PageRank** 来决定哪些代码最值得给 LLM 看。

```
你的代码库
    │
    ▼
tree-sitter 解析 AST
    │
    ▼
构建引用图（文件→函数→类）
    │
    ▼
PageRank 排序（用户提到的代码权重 ×50）
    │
    ▼
在 token 预算内贪心填充 → RepoMap
```

**关键数字**：
- 用户提到的文件相关代码获得 **50 倍权重加成**
- RepoMap 有独立的 **1024 token 预算**，不挤占文件内容空间
- 整个 RepoMap 原始实现约 2000 行，我们的 demo 复现约 150 行

**为什么这很重要**：当你的项目有 500 个文件时，LLM 不可能全看。aider 的做法等于给 LLM 装了一个"代码 GPS"——它永远知道项目里最相关的 5% 在哪。

> demo 代码：[demos/aider/repomap/](https://github.com/7hinkDifferent/agent-cracker/tree/main/demos/aider/repomap)

---

## 发现二：Codex-CLI 的安全不是"问你一下"，是三层防御

很多 agent 的安全模型就是弹个确认框。Codex-CLI 完全不同——它有 **三层嵌套的安全门**：

| 层级 | 机制 | 作用 |
|------|------|------|
| **第一层** | 审批策略（ExecPolicy） | 50+ 危险命令前缀黑名单 + 模式匹配 |
| **第二层** | 平台沙箱（Seatbelt/Landlock） | 运��时生成沙箱配置，物理限制文件系统访问 |
| **第三层** | 网络代理 | 拦截所有网络请求，只允许白名单域名 |

即使 LLM 生成了 `rm -rf /`，第一层就会拦住。即使绕过了第一层，沙箱让它只能访问当前目录。即使读了代码想外传，网络代理不让它连外网。

**三种运行模式的权限递进**：

```
Suggest      → 编辑需审批 + 命令需审批 + 沙箱 + 网络限制
Auto-Edit    → 编辑自动执行 + 命令需审批 + 沙箱 + 网络限制
Full-Auto    → 全部自动执行 + 沙箱 + 网络限制（沙箱永远在）
```

注意：即使在 Full-Auto 模式，沙箱和网络限制依然存在。这就是 **Defense-in-Depth**（纵深防御）。

> demo 代码：[demos/codex-cli/approval-policy/](https://github.com/7hinkDifferent/agent-cracker/tree/main/demos/codex-cli/approval-policy)

---

## 发现三：Pi-Agent 让你在 Agent 思考时随时插嘴

用过 ChatGPT 的人都知道那个感觉——你发了消息，然后只能等。发现方向错了？只能等它说完再纠正。

Pi-Agent 用 **双消息队列** 解决了这个问题：

```
用户输入
    │
    ├── Ctrl+Z → Steering Queue（立即中断）
    │              Agent 停止当前 tool → 读取你的消息 → 改变方向
    │
    └── 正常输入 → Follow-up Queue（排队等待）
                   Agent 完成当前任务后再处理
```

这不是"暂停/恢复"，是真正的 **实时协作**。你可以在 Agent 执行 shell 命令的间隙说"等等，别改那个文件"，它会立即听到。

**另一个让我惊艳的设计**：Pi-Agent 的所有文件操作（read、edit、bash、grep）都通过 **Pluggable Ops 接口** 抽象。换一个 adapter，同样的 agent 可以操作本地文件系统、SSH 远程服务器或 Docker 容器，零代码修改。

> demo 代码：[demos/pi-agent/steering-queue/](https://github.com/7hinkDifferent/agent-cracker/tree/main/demos/pi-agent/steering-queue)

---

## 横向对比：三种设计哲学

| | aider | codex-cli | pi-agent |
|---|-------|-----------|----------|
| **核心超能力** | 理解代码拓扑（PageRank） | 安全真正可靠（三层防御） | 实时协作（双队列） |
| **语言** | Python | Rust + TypeScript | TypeScript |
| **Agent Loop** | 三层嵌套循环 | tokio 异步多路复用 | 双层循环 + steering |
| **编辑策略** | 12+ 种编辑格式 | unified diff | 精确替换 + 模糊匹配 |
| **适合谁** | 想要最强代码理解 | 需要生产环境安全 | 追求流畅交互体验 |

## 每个 Agent 教会我的一件事

- **aider 教会我**：领域特定算法（PageRank on code）比通用方案强得多
- **codex-cli 教会我**：安全必须内建（baked-in），不能外挂（bolted-on）
- **pi-agent 教会我**：系统级 UX 改进（双队列）比 UI 美化有价值得多

---

## 动手试试

所有 demo 都是 100-200 行的独立可运行代码：

```bash
git clone https://github.com/7hinkDifferent/agent-cracker.git
cd agent-cracker

# 跑 aider 的 SEARCH/REPLACE 解析器
cd demos/aider/search-replace && uv run python main.py

# 跑 codex-cli 的审批策略
cd demos/codex-cli/approval-policy && uv run python main.py

# 跑 pi-agent 的 steering 队列
cd demos/pi-agent/steering-queue && npx tsx main.ts
```

完整项目：[github.com/7hinkDifferent/agent-cracker](https://github.com/7hinkDifferent/agent-cracker)

---

*本文基于 [Agent Cracker](https://github.com/7hinkDifferent/agent-cracker) 项目的分析成果。项目持续更新中，目前已覆盖 11 个 agent、16 个机制 demo。*
