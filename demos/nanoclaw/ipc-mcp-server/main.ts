/**
 * NanoClaw IPC MCP Server — 机制 Demo
 *
 * 复现容器内 MCP 工具服务器的核心机制:
 *   1. Tool 注册 + zod schema 校验
 *   2. Atomic IPC 文件写入 (tmp → rename)
 *   3. 权限检查 (isMain gate)
 *   4. 输入验证 (cron/interval/once)
 *
 * 基于 container/agent-runner/src/ipc-mcp-stdio.ts (285 行)
 *
 * 运行: npx tsx main.ts
 */

import fs from "fs";
import path from "path";
import os from "os";

// ---------------------------------------------------------------------------
// Mini MCP framework (replaces @modelcontextprotocol/sdk)
// ---------------------------------------------------------------------------

interface ToolSchema {
  [key: string]: { type: string; description?: string; enum?: string[]; optional?: boolean };
}

interface ToolResult {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
}

type ToolHandler = (args: Record<string, unknown>) => Promise<ToolResult>;

interface RegisteredTool {
  name: string;
  description: string;
  schema: ToolSchema;
  handler: ToolHandler;
}

class MiniMcpServer {
  name: string;
  private tools = new Map<string, RegisteredTool>();

  constructor(opts: { name: string; version: string }) {
    this.name = opts.name;
  }

  tool(
    name: string,
    description: string,
    schema: ToolSchema,
    handler: ToolHandler,
  ): void {
    this.tools.set(name, { name, description, schema, handler });
  }

  listTools(): string[] {
    return Array.from(this.tools.keys());
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<ToolResult> {
    const tool = this.tools.get(name);
    if (!tool) {
      return { content: [{ type: "text", text: `Unknown tool: ${name}` }], isError: true };
    }

    // Schema validation (simplified)
    for (const [key, def] of Object.entries(tool.schema)) {
      if (!def.optional && args[key] === undefined) {
        return {
          content: [{ type: "text", text: `Missing required arg: ${key}` }],
          isError: true,
        };
      }
      if (def.enum && args[key] && !def.enum.includes(args[key] as string)) {
        return {
          content: [{
            type: "text",
            text: `Invalid value for ${key}: ${args[key]}. Must be one of: ${def.enum.join(", ")}`,
          }],
          isError: true,
        };
      }
    }

    return tool.handler(args);
  }
}

// ---------------------------------------------------------------------------
// Atomic IPC file writer (mirrors writeIpcFile in original)
// ---------------------------------------------------------------------------

function writeIpcFile(dir: string, data: object): string {
  fs.mkdirSync(dir, { recursive: true });
  const filename = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}.json`;
  const filepath = path.join(dir, filename);

  // Atomic write: temp file then rename (prevents reading half-written files)
  const tempPath = `${filepath}.tmp`;
  fs.writeFileSync(tempPath, JSON.stringify(data, null, 2));
  fs.renameSync(tempPath, filepath);

  return filename;
}

// ---------------------------------------------------------------------------
// NanoClaw MCP tools (mirrors ipc-mcp-stdio.ts)
// ---------------------------------------------------------------------------

function createNanoClawServer(opts: {
  ipcDir: string;
  chatJid: string;
  groupFolder: string;
  isMain: boolean;
}): MiniMcpServer {
  const { ipcDir, chatJid, groupFolder, isMain } = opts;
  const messagesDir = path.join(ipcDir, "messages");
  const tasksDir = path.join(ipcDir, "tasks");

  const server = new MiniMcpServer({ name: "nanoclaw", version: "1.0.0" });

  // Tool 1: send_message — 向用户/群组发送即时消息
  server.tool(
    "send_message",
    "Send a message to the user or group immediately.",
    {
      text: { type: "string", description: "The message text to send" },
      sender: { type: "string", description: "Role/identity name", optional: true },
    },
    async (args) => {
      writeIpcFile(messagesDir, {
        type: "message",
        chatJid,
        text: args.text,
        sender: args.sender || undefined,
        groupFolder,
        timestamp: new Date().toISOString(),
      });
      return { content: [{ type: "text", text: "Message sent." }] };
    },
  );

  // Tool 2: schedule_task — 创建定时/定期任务
  server.tool(
    "schedule_task",
    "Schedule a recurring or one-time task.",
    {
      prompt: { type: "string", description: "What the agent should do" },
      schedule_type: { type: "string", enum: ["cron", "interval", "once"] },
      schedule_value: { type: "string", description: "cron/ms/timestamp" },
      context_mode: { type: "string", enum: ["group", "isolated"], optional: true },
    },
    async (args) => {
      // Validate schedule_value
      if (args.schedule_type === "interval") {
        const ms = parseInt(args.schedule_value as string, 10);
        if (isNaN(ms) || ms <= 0) {
          return {
            content: [{ type: "text", text: `Invalid interval: "${args.schedule_value}". Must be positive ms.` }],
            isError: true,
          };
        }
      } else if (args.schedule_type === "once") {
        const val = args.schedule_value as string;
        if (/[Zz]$/.test(val)) {
          return {
            content: [{ type: "text", text: `Must be local time without Z suffix. Got "${val}".` }],
            isError: true,
          };
        }
      }

      const filename = writeIpcFile(tasksDir, {
        type: "schedule_task",
        prompt: args.prompt,
        schedule_type: args.schedule_type,
        schedule_value: args.schedule_value,
        context_mode: args.context_mode || "group",
        targetJid: chatJid,
        createdBy: groupFolder,
        timestamp: new Date().toISOString(),
      });
      return {
        content: [{ type: "text", text: `Task scheduled (${filename}): ${args.schedule_type} - ${args.schedule_value}` }],
      };
    },
  );

  // Tool 3: list_tasks
  server.tool("list_tasks", "List all scheduled tasks.", {}, async () => {
    const tasksFile = path.join(ipcDir, "current_tasks.json");
    if (!fs.existsSync(tasksFile)) {
      return { content: [{ type: "text", text: "No scheduled tasks." }] };
    }
    const tasks = JSON.parse(fs.readFileSync(tasksFile, "utf-8"));
    const filtered = isMain ? tasks : tasks.filter((t: { groupFolder: string }) => t.groupFolder === groupFolder);
    const text = filtered.map((t: { id: string; prompt: string }) => `- [${t.id}] ${t.prompt.slice(0, 50)}`).join("\n");
    return { content: [{ type: "text", text: text || "No scheduled tasks." }] };
  });

  // Tool 4/5: pause_task / resume_task
  for (const action of ["pause", "resume", "cancel"] as const) {
    server.tool(
      `${action}_task`,
      `${action.charAt(0).toUpperCase() + action.slice(1)} a scheduled task.`,
      { task_id: { type: "string", description: "The task ID" } },
      async (args) => {
        writeIpcFile(tasksDir, {
          type: `${action}_task`,
          taskId: args.task_id,
          groupFolder,
          isMain,
          timestamp: new Date().toISOString(),
        });
        return { content: [{ type: "text", text: `Task ${args.task_id} ${action} requested.` }] };
      },
    );
  }

  // Tool 6: register_group (main only)
  server.tool(
    "register_group",
    "Register a new WhatsApp group. Main group only.",
    {
      jid: { type: "string" },
      name: { type: "string" },
      folder: { type: "string" },
      trigger: { type: "string" },
    },
    async (args) => {
      if (!isMain) {
        return { content: [{ type: "text", text: "Only main group can register." }], isError: true };
      }
      writeIpcFile(tasksDir, {
        type: "register_group", jid: args.jid, name: args.name,
        folder: args.folder, trigger: args.trigger,
        timestamp: new Date().toISOString(),
      });
      return { content: [{ type: "text", text: `Group "${args.name}" registered.` }] };
    },
  );

  return server;
}

// ---------------------------------------------------------------------------
// Demo runner
// ---------------------------------------------------------------------------

async function demo_tool_registration() {
  console.log("=".repeat(60));
  console.log("Demo 1: Tool 注册 — 6 个 MCP 工具");
  console.log("=".repeat(60));

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nanoclaw-mcp-"));
  const server = createNanoClawServer({
    ipcDir: tmpDir, chatJid: "main@g.us", groupFolder: "main", isMain: true,
  });

  console.log(`\n  注册的工具: ${server.listTools().join(", ")}`);
  console.log(`  工具总数: ${server.listTools().length}`);
  console.log();
  fs.rmSync(tmpDir, { recursive: true });
}

async function demo_send_message() {
  console.log("=".repeat(60));
  console.log("Demo 2: send_message — 即时消息 + Atomic IPC");
  console.log("=".repeat(60));

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nanoclaw-mcp-"));
  const server = createNanoClawServer({
    ipcDir: tmpDir, chatJid: "team@g.us", groupFolder: "team", isMain: false,
  });

  const result = await server.callTool("send_message", { text: "任务进展: 50% 完成" });
  console.log(`\n  结果: ${result.content[0].text}`);

  // Check IPC file
  const msgDir = path.join(tmpDir, "messages");
  const files = fs.readdirSync(msgDir);
  console.log(`  IPC 文件: ${files[0]}`);
  const data = JSON.parse(fs.readFileSync(path.join(msgDir, files[0]), "utf-8"));
  console.log(`  内容: type=${data.type}, text="${data.text}", chatJid=${data.chatJid}`);
  console.log(`  Atomic 写入: .tmp 文件已重命名为 .json`);
  console.log();
  fs.rmSync(tmpDir, { recursive: true });
}

async function demo_schedule_validation() {
  console.log("=".repeat(60));
  console.log("Demo 3: schedule_task — 输入验证");
  console.log("=".repeat(60));

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nanoclaw-mcp-"));
  const server = createNanoClawServer({
    ipcDir: tmpDir, chatJid: "main@g.us", groupFolder: "main", isMain: true,
  });

  // Valid cron
  const r1 = await server.callTool("schedule_task", {
    prompt: "每天早上 9 点发天气预报", schedule_type: "cron",
    schedule_value: "0 9 * * *", context_mode: "isolated",
  });
  console.log(`\n  有效 cron: ${r1.content[0].text}`);

  // Invalid interval
  const r2 = await server.callTool("schedule_task", {
    prompt: "test", schedule_type: "interval", schedule_value: "-1",
  });
  console.log(`  无效 interval: ${r2.content[0].text} (isError=${r2.isError})`);

  // UTC timestamp rejected
  const r3 = await server.callTool("schedule_task", {
    prompt: "test", schedule_type: "once", schedule_value: "2026-03-01T09:00:00Z",
  });
  console.log(`  UTC 时间戳: ${r3.content[0].text} (isError=${r3.isError})`);
  console.log();
  fs.rmSync(tmpDir, { recursive: true });
}

async function demo_permission_gate() {
  console.log("=".repeat(60));
  console.log("Demo 4: 权限控制 — 非 main 无法注册群组");
  console.log("=".repeat(60));

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nanoclaw-mcp-"));

  // Non-main tries to register
  const nonMain = createNanoClawServer({
    ipcDir: tmpDir, chatJid: "team@g.us", groupFolder: "team", isMain: false,
  });
  const r1 = await nonMain.callTool("register_group", {
    jid: "new@g.us", name: "New", folder: "new", trigger: "@Andy",
  });
  console.log(`\n  非 main 注册: ${r1.content[0].text} (isError=${r1.isError})`);

  // Main can register
  const main = createNanoClawServer({
    ipcDir: tmpDir, chatJid: "main@g.us", groupFolder: "main", isMain: true,
  });
  const r2 = await main.callTool("register_group", {
    jid: "new@g.us", name: "Family", folder: "family", trigger: "@Andy",
  });
  console.log(`  main 注册: ${r2.content[0].text}`);
  console.log();
  fs.rmSync(tmpDir, { recursive: true });
}

async function demo_list_tasks() {
  console.log("=".repeat(60));
  console.log("Demo 5: list_tasks — 权限过滤");
  console.log("=".repeat(60));

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nanoclaw-mcp-"));

  // Write mock tasks snapshot
  fs.writeFileSync(path.join(tmpDir, "current_tasks.json"), JSON.stringify([
    { id: "t1", groupFolder: "main", prompt: "每日报告" },
    { id: "t2", groupFolder: "team", prompt: "代码审查提醒" },
    { id: "t3", groupFolder: "main", prompt: "系统健康检查" },
  ]));

  const main = createNanoClawServer({
    ipcDir: tmpDir, chatJid: "main@g.us", groupFolder: "main", isMain: true,
  });
  const r1 = await main.callTool("list_tasks", {});
  console.log(`\n  Main 看到的任务:\n${r1.content[0].text}`);

  const team = createNanoClawServer({
    ipcDir: tmpDir, chatJid: "team@g.us", groupFolder: "team", isMain: false,
  });
  const r2 = await team.callTool("list_tasks", {});
  console.log(`\n  Team 看到的任务:\n${r2.content[0].text}`);
  console.log();
  fs.rmSync(tmpDir, { recursive: true });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  console.log("NanoClaw IPC MCP Server — 机制 Demo\n");
  await demo_tool_registration();
  await demo_send_message();
  await demo_schedule_validation();
  await demo_permission_gate();
  await demo_list_tasks();
  console.log("✓ 所有 demo 完成");
}

main();
