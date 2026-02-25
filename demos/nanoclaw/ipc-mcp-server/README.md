# ipc-mcp-server — 容器内 MCP 工具服务器

## 目标

复现 NanoClaw 容器内的 MCP 工具服务器：7 个自定义 Tool 通过文件 IPC 与 host 通信。

## MVP 角色

MCP Server 是容器内 agent 与 host 世界的"桥梁"。Claude SDK 调用 MCP 工具时，工具将请求写为 IPC JSON 文件，host 的 IPC Watcher 读取并执行（发消息、创建任务、注册群组）。

## 原理

```
Claude Agent (容器内)
  │ 选择 tool（如 send_message）
  ▼
Claude SDK query() → MCP 工具调用
  │
  ▼
ipc-mcp-stdio.ts (StdioServerTransport)
  │ 1. zod 参数校验
  │ 2. 权限检查 (isMain gate)
  │ 3. Atomic IPC 写入: .tmp → rename → .json
  │    /workspace/ipc/messages/  (消息)
  │    /workspace/ipc/tasks/     (任务/群组操作)
  ▼
Host: ipc.ts (1s poll)
  │ 读取 JSON → 验证来源 → 执行操作
  ▼
WhatsApp / SQLite / 群组注册
```

**Atomic 写入**: 先写 `.tmp` 文件再 `rename`，避免 host 读到半写的 JSON。

**权限隔离**: `chatJid`/`groupFolder`/`isMain` 通过环境变量注入，非 main 组群无法跨组操作。

## 运行

```bash
npx tsx main.ts
```

无外部依赖。使用内置 Mini MCP framework 模拟 `@modelcontextprotocol/sdk`。

## 为何选择 TypeScript

原实现运行在 Docker 容器内，依赖 `@modelcontextprotocol/sdk` 的 `StdioServerTransport`。Demo 用 TypeScript 保持与原始代码的一致性，但替换了 SDK 依赖为轻量 mock。

## 文件结构

```
ipc-mcp-server/
├── README.md       # 本文件
└── main.ts         # Demo: Mini MCP framework + 7 tools + 5 个演示场景
```

## 关键代码解读

### Atomic IPC 写入

```typescript
function writeIpcFile(dir: string, data: object): string {
  const filename = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}.json`;
  const filepath = path.join(dir, filename);
  const tempPath = `${filepath}.tmp`;          // 1. 写临时文件
  fs.writeFileSync(tempPath, JSON.stringify(data, null, 2));
  fs.renameSync(tempPath, filepath);            // 2. 原子重命名
  return filename;
}
```

### 权限门控

```typescript
// register_group — 仅 main 组群可用
if (!isMain) {
  return { content: [{ type: "text", text: "Only main group can register." }], isError: true };
}
```

### 输入验证（schedule_task）

```typescript
// UTC 时间戳被拒绝 — 必须用本地时间
if (args.schedule_type === "once" && /[Zz]$/.test(val)) {
  return { isError: true, ... };
}
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| MCP 框架 | `@modelcontextprotocol/sdk` + `StdioServerTransport` | Mini MCP framework (内置) |
| 参数校验 | zod schema | 简化的类型+枚举校验 |
| Cron 验证 | `cron-parser` 库 | 未验证 cron 语法 |
| 传输协议 | stdio (JSON-RPC) | 直接函数调用 |
| 环境变量 | `process.env.NANOCLAW_*` | 构造函数参数 |

## 相关文档

- 分析文档: [docs/nanoclaw.md — D3 Tool 系统](../../docs/nanoclaw.md#3-toolaction-系统)
- 原始源码: `projects/nanoclaw/container/agent-runner/src/ipc-mcp-stdio.ts` (285 行)
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
