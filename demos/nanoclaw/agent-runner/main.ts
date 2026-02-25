/**
 * NanoClaw Agent Runner — 机制 Demo
 *
 * 复现容器内 Agent 运行器的核心机制:
 *   1. MessageStream (push-based AsyncIterable)
 *   2. query 循环 + IPC 消息管道
 *   3. PreCompact 对话归档 (JSONL → Markdown)
 *   4. Bash 命令密钥清理 hook
 *   5. _close sentinel 退出
 *
 * 基于 container/agent-runner/src/index.ts (588 行)
 *
 * 运行: npx tsx main.ts
 */

import fs from "fs";
import path from "path";
import os from "os";

// ---------------------------------------------------------------------------
// MessageStream — push-based AsyncIterable
// ---------------------------------------------------------------------------

/**
 * Push-based async iterable for streaming messages to the SDK.
 *
 * 核心设计：
 * - push() 从外部注入消息（IPC 管道）
 * - end() 结束流（_close sentinel 或 query 完成）
 * - async iterator 在无消息时阻塞等待
 *
 * 在原实现中，这让 Claude SDK 的 isSingleUserTurn=false，
 * 使 query 保持活跃以接收后续消息。
 */
interface UserMessage {
  type: "user";
  content: string;
}

class MessageStream {
  private queue: UserMessage[] = [];
  private waiting: (() => void) | null = null;
  private done = false;

  push(text: string): void {
    this.queue.push({ type: "user", content: text });
    this.waiting?.();
  }

  end(): void {
    this.done = true;
    this.waiting?.();
  }

  async *[Symbol.asyncIterator](): AsyncGenerator<UserMessage> {
    while (true) {
      while (this.queue.length > 0) {
        yield this.queue.shift()!;
      }
      if (this.done) return;
      await new Promise<void>((r) => { this.waiting = r; });
      this.waiting = null;
    }
  }
}

// ---------------------------------------------------------------------------
// IPC input polling (simulated with temp directory)
// ---------------------------------------------------------------------------

const CLOSE_SENTINEL = "_close";

function drainIpcInput(inputDir: string): string[] {
  try {
    const files = fs.readdirSync(inputDir).filter((f) => f.endsWith(".json")).sort();
    const messages: string[] = [];
    for (const file of files) {
      const filePath = path.join(inputDir, file);
      try {
        const data = JSON.parse(fs.readFileSync(filePath, "utf-8"));
        fs.unlinkSync(filePath);
        if (data.type === "message" && data.text) {
          messages.push(data.text);
        }
      } catch {
        try { fs.unlinkSync(filePath); } catch { /* ignore */ }
      }
    }
    return messages;
  } catch {
    return [];
  }
}

function shouldClose(inputDir: string): boolean {
  const sentinel = path.join(inputDir, CLOSE_SENTINEL);
  if (fs.existsSync(sentinel)) {
    try { fs.unlinkSync(sentinel); } catch { /* ignore */ }
    return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// PreCompact hook — conversation archiving
// ---------------------------------------------------------------------------

interface ParsedMessage {
  role: "user" | "assistant";
  content: string;
}

function parseTranscript(content: string): ParsedMessage[] {
  const messages: ParsedMessage[] = [];
  for (const line of content.split("\n")) {
    if (!line.trim()) continue;
    try {
      const entry = JSON.parse(line);
      if (entry.type === "user" && entry.message?.content) {
        const text = typeof entry.message.content === "string"
          ? entry.message.content
          : entry.message.content.map((c: { text?: string }) => c.text || "").join("");
        if (text) messages.push({ role: "user", content: text });
      } else if (entry.type === "assistant" && entry.message?.content) {
        const textParts = entry.message.content
          .filter((c: { type: string }) => c.type === "text")
          .map((c: { text: string }) => c.text);
        if (textParts.join("")) messages.push({ role: "assistant", content: textParts.join("") });
      }
    } catch { /* skip non-JSON lines */ }
  }
  return messages;
}

function archiveConversation(transcriptContent: string, outputDir: string, title?: string): string | null {
  const messages = parseTranscript(transcriptContent);
  if (messages.length === 0) return null;

  fs.mkdirSync(outputDir, { recursive: true });
  const date = new Date().toISOString().split("T")[0];
  const safeName = (title || "conversation")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 50);
  const filename = `${date}-${safeName}.md`;
  const filePath = path.join(outputDir, filename);

  const lines = [`# ${title || "Conversation"}`, "", `Archived: ${new Date().toLocaleString()}`, "", "---", ""];
  for (const msg of messages) {
    const sender = msg.role === "user" ? "User" : "Assistant";
    const content = msg.content.length > 2000 ? msg.content.slice(0, 2000) + "..." : msg.content;
    lines.push(`**${sender}**: ${content}`, "");
  }

  fs.writeFileSync(filePath, lines.join("\n"));
  return filePath;
}

// ---------------------------------------------------------------------------
// Bash sanitize hook — strip API keys from subprocesses
// ---------------------------------------------------------------------------

const SECRET_ENV_VARS = ["ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"];

function sanitizeBashCommand(command: string): string {
  const unsetPrefix = `unset ${SECRET_ENV_VARS.join(" ")} 2>/dev/null; `;
  return unsetPrefix + command;
}

// ---------------------------------------------------------------------------
// Mock query loop (simulates Claude SDK query())
// ---------------------------------------------------------------------------

interface MockQueryResult {
  sessionId: string;
  result: string | null;
}

async function mockQuery(prompt: string, sessionId?: string): Promise<MockQueryResult> {
  // Simulate LLM processing delay
  await new Promise((r) => setTimeout(r, 50));
  const newSessionId = sessionId || `sess-${Date.now().toString(36)}`;
  return {
    sessionId: newSessionId,
    result: `[Mock response to: ${prompt.slice(0, 50)}...]`,
  };
}

// Sentinel markers
const OUTPUT_START = "---NANOCLAW_OUTPUT_START---";
const OUTPUT_END = "---NANOCLAW_OUTPUT_END---";

function writeOutput(output: { status: string; result: string | null; newSessionId?: string }): void {
  console.log(`    ${OUTPUT_START}`);
  console.log(`    ${JSON.stringify(output)}`);
  console.log(`    ${OUTPUT_END}`);
}

// ---------------------------------------------------------------------------
// Demos
// ---------------------------------------------------------------------------

async function demo_message_stream() {
  console.log("=".repeat(60));
  console.log("Demo 1: MessageStream — push-based AsyncIterable");
  console.log("=".repeat(60));

  const stream = new MessageStream();

  // Push messages from "outside" (simulating IPC pipe)
  stream.push("第一条消息: @Andy 帮我查天气");

  // Schedule more messages after a delay (simulating IPC polling)
  setTimeout(() => stream.push("第二条消息: 还有明天的呢？"), 30);
  setTimeout(() => stream.end(), 60);

  console.log("\n  异步迭代 MessageStream:");
  let count = 0;
  for await (const msg of stream) {
    count++;
    console.log(`    [msg ${count}] ${msg.content}`);
  }
  console.log(`  流结束, 共 ${count} 条消息\n`);
}

async function demo_query_loop() {
  console.log("=".repeat(60));
  console.log("Demo 2: Query 循环 + IPC 消息管道");
  console.log("=".repeat(60));

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nanoclaw-runner-"));
  const inputDir = path.join(tmpDir, "input");
  fs.mkdirSync(inputDir, { recursive: true });

  // Write a follow-up message that will be discovered during query 1 → 2
  setTimeout(() => {
    const msgFile = path.join(inputDir, `${Date.now()}-msg.json`);
    fs.writeFileSync(msgFile, JSON.stringify({ type: "message", text: "后续消息: 帮我改一下代码" }));
  }, 80);

  // Write _close sentinel after query 2
  setTimeout(() => {
    fs.writeFileSync(path.join(inputDir, CLOSE_SENTINEL), "");
  }, 200);

  let sessionId: string | undefined;
  let prompt = "初始消息: @Andy 帮我写个函数";
  let queryNum = 0;

  console.log("\n  Query 循环 (模拟容器内 agent-runner):");
  while (true) {
    queryNum++;
    console.log(`\n  --- Query #${queryNum} ---`);
    console.log(`    prompt: "${prompt.slice(0, 50)}..."`);

    const result = await mockQuery(prompt, sessionId);
    sessionId = result.sessionId;

    writeOutput({ status: "success", result: result.result, newSessionId: sessionId });
    console.log(`    session: ${sessionId}`);

    // Check for _close
    if (shouldClose(inputDir)) {
      console.log("    _close sentinel 检测到, 退出循环");
      break;
    }

    // Wait for IPC message (simplified: just check once after delay)
    await new Promise((r) => setTimeout(r, 100));
    const messages = drainIpcInput(inputDir);

    if (messages.length > 0) {
      prompt = messages.join("\n");
      console.log(`    收到 IPC 消息 (${messages.length} 条), 继续循环`);
    } else if (shouldClose(inputDir)) {
      console.log("    _close sentinel 检测到, 退出循环");
      break;
    } else {
      console.log("    无后续消息, 退出循环");
      break;
    }
  }
  console.log(`\n  循环结束, 共执行 ${queryNum} 次 query`);
  fs.rmSync(tmpDir, { recursive: true });
  console.log();
}

async function demo_precompact() {
  console.log("=".repeat(60));
  console.log("Demo 3: PreCompact — 对话归档 (JSONL → Markdown)");
  console.log("=".repeat(60));

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nanoclaw-archive-"));

  // Mock JSONL transcript
  const transcript = [
    JSON.stringify({ type: "user", message: { role: "user", content: "@Andy 帮我查天气" } }),
    JSON.stringify({ type: "assistant", message: { content: [{ type: "text", text: "北京今天 25°C，晴朗。" }] } }),
    JSON.stringify({ type: "user", message: { role: "user", content: "明天呢？" } }),
    JSON.stringify({ type: "assistant", message: { content: [{ type: "text", text: "明天 22°C，多云。" }] } }),
    "invalid json line — should be skipped",
  ].join("\n");

  const outputDir = path.join(tmpDir, "conversations");
  const filePath = archiveConversation(transcript, outputDir, "天气查询对话");

  console.log(`\n  归档到: ${filePath}`);
  if (filePath) {
    const content = fs.readFileSync(filePath, "utf-8");
    console.log("  Markdown 内容:");
    for (const line of content.split("\n").slice(0, 12)) {
      console.log(`    ${line}`);
    }
  }
  fs.rmSync(tmpDir, { recursive: true });
  console.log();
}

async function demo_bash_sanitize() {
  console.log("=".repeat(60));
  console.log("Demo 4: Bash 密钥清理 — PreToolUse hook");
  console.log("=".repeat(60));

  const original = 'curl https://api.example.com -H "Authorization: $ANTHROPIC_API_KEY"';
  const sanitized = sanitizeBashCommand(original);

  console.log(`\n  原始命令:\n    ${original}`);
  console.log(`  清理后:\n    ${sanitized}`);
  console.log("  (unset 确保子进程无法读取 API 密钥)");
  console.log();
}

async function demo_ipc_drain() {
  console.log("=".repeat(60));
  console.log("Demo 5: IPC Drain — 文件轮询 + 原子消费");
  console.log("=".repeat(60));

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nanoclaw-ipc-"));
  fs.mkdirSync(tmpDir, { recursive: true });

  // Write multiple IPC files (simulating host writing messages)
  for (let i = 0; i < 3; i++) {
    const file = path.join(tmpDir, `${Date.now() + i}-msg${i}.json`);
    fs.writeFileSync(file, JSON.stringify({ type: "message", text: `消息 ${i + 1}` }));
  }

  const before = fs.readdirSync(tmpDir).filter((f) => f.endsWith(".json")).length;
  console.log(`\n  写入 ${before} 个 IPC 文件`);

  const messages = drainIpcInput(tmpDir);
  console.log(`  drain 读取: ${messages.length} 条消息`);
  messages.forEach((m, i) => console.log(`    [${i}] ${m}`));

  const after = fs.readdirSync(tmpDir).filter((f) => f.endsWith(".json")).length;
  console.log(`  drain 后剩余文件: ${after} (已消费)`);
  fs.rmSync(tmpDir, { recursive: true });
  console.log();
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  console.log("NanoClaw Agent Runner — 机制 Demo\n");
  await demo_message_stream();
  await demo_query_loop();
  await demo_precompact();
  await demo_bash_sanitize();
  await demo_ipc_drain();
  console.log("✓ 所有 demo 完成");
}

main();
