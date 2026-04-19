// @ts-nocheck

import { existsSync, readFileSync, readdirSync } from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

type ProjectStatus = {
  summary: string;
  widgetLines: string[];
};

function splitLines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line.length > 0);
}

function truncateText(text: string, maxLength = 600): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength - 1)}…`;
}

function isTrackedDocOrConfig(file: string): boolean {
  return (
    file === "CLAUDE.md" ||
    file === "AGENTS.md" ||
    file === "README.md" ||
    file === "README.en.md" ||
    file === "agents.yaml" ||
    file === "package.json" ||
    file.startsWith("docs/") ||
    file.startsWith(".claude/") ||
    file.startsWith(".pi/") ||
    file.startsWith(".agents/") ||
    /^demos\/[^/]+\/README\.md$/.test(file)
  );
}

function parseAgentsYamlStatuses(yamlPath: string): Array<{ name: string; status: string }> {
  const content = readFileSync(yamlPath, "utf8");
  const lines = content.split(/\r?\n/);
  const items: Array<{ name: string; status: string }> = [];
  let currentName = "";

  for (const line of lines) {
    const nameMatch = line.match(/^\s*-\s*name:\s*(.+)\s*$/);
    if (nameMatch) {
      currentName = nameMatch[1].trim();
      continue;
    }

    const statusMatch = line.match(/^\s*status:\s*(.+)\s*$/);
    if (statusMatch && currentName) {
      items.push({ name: currentName, status: statusMatch[1].trim() });
    }
  }

  return items;
}

function parseAgentsYamlCommits(yamlPath: string): Array<{ name: string; analyzedCommit: string }> {
  const content = readFileSync(yamlPath, "utf8");
  const lines = content.split(/\r?\n/);
  const items: Array<{ name: string; analyzedCommit: string }> = [];
  let currentName = "";

  for (const line of lines) {
    const nameMatch = line.match(/^\s*-\s*name:\s*(.+)\s*$/);
    if (nameMatch) {
      currentName = nameMatch[1].trim();
      continue;
    }

    const commitMatch = line.match(/^\s*analyzed_commit:\s*([0-9a-fA-F]{7,40})\s*$/);
    if (commitMatch && currentName) {
      items.push({ name: currentName, analyzedCommit: commitMatch[1].trim() });
    }
  }

  return items;
}

function countDemoEntrypoints(rootDir: string): number {
  if (!existsSync(rootDir)) return 0;

  const targets = new Set(["main.py", "repomap.py", "main.ts", "index.ts", "main.rs"]);
  let count = 0;

  function walk(dir: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const absolute = path.join(dir, entry.name);
      if (absolute.includes(`${path.sep}TEMPLATE${path.sep}`)) continue;
      if (entry.isDirectory()) {
        walk(absolute);
      } else if (targets.has(entry.name)) {
        count += 1;
      }
    }
  }

  walk(rootDir);
  return count;
}

async function getRepoRoot(pi: ExtensionAPI, cwd: string): Promise<string | undefined> {
  const result = await pi.exec("git", ["rev-parse", "--show-toplevel"], { cwd, timeout: 10_000 });
  if (result.code !== 0) return undefined;
  const root = result.stdout.trim();
  return root || undefined;
}

async function getGitHead(pi: ExtensionAPI, cwd: string): Promise<string | undefined> {
  const result = await pi.exec("git", ["rev-parse", "HEAD"], { cwd, timeout: 10_000 });
  if (result.code !== 0) return undefined;
  const head = result.stdout.trim();
  return head || undefined;
}

async function buildProjectStatus(pi: ExtensionAPI, cwd: string): Promise<ProjectStatus | undefined> {
  const yamlPath = path.join(cwd, "agents.yaml");
  if (!existsSync(yamlPath)) return undefined;

  const statuses = parseAgentsYamlStatuses(yamlPath);
  const demos = countDemoEntrypoints(path.join(cwd, "demos"));
  const commitItems = parseAgentsYamlCommits(yamlPath);
  let driftCount = 0;

  for (const item of commitItems) {
    const projectDir = path.join(cwd, "projects", item.name);
    if (!existsSync(projectDir)) continue;
    const head = await getGitHead(pi, projectDir);
    if (head && head !== item.analyzedCommit) {
      driftCount += 1;
    }
  }

  const statusLines = statuses.map((item) => `- ${item.name}: ${item.status}`);
  const summaryLines = [
    "Current project status:",
    ...statusLines,
    `Total demos: ${demos}`,
  ];

  if (driftCount > 0) {
    summaryLines.push(
      `⚠️ ${driftCount} agent(s) have local drift (submodule HEAD ≠ analyzed_commit). Run /check-updates to inspect.`,
    );
  }

  const widgetLines = [
    `Agents: ${statuses.length}`,
    `Demos: ${demos}`,
    driftCount > 0 ? `Drift: ${driftCount}` : "Drift: 0",
    statuses.length > 0 ? `Latest: ${statuses[statuses.length - 1].name}=${statuses[statuses.length - 1].status}` : "",
  ].filter(Boolean);

  return {
    summary: summaryLines.join("\n"),
    widgetLines,
  };
}

async function getChangedFiles(pi: ExtensionAPI, cwd: string, staged: boolean): Promise<string[]> {
  const args = staged ? ["diff", "--cached", "--name-only"] : ["diff", "--name-only"];
  const result = await pi.exec("git", args, { cwd, timeout: 10_000 });
  if (result.code !== 0) return [];
  return splitLines(result.stdout);
}

async function runPreCommitChecks(pi: ExtensionAPI, cwd: string): Promise<string[]> {
  const repoRoot = await getRepoRoot(pi, cwd);
  if (!repoRoot) return [];

  const unstaged = await getChangedFiles(pi, repoRoot, false);
  const staged = await getChangedFiles(pi, repoRoot, true);
  const issues: string[] = [];

  const unstagedDocs = unstaged.filter(isTrackedDocOrConfig);
  if (unstagedDocs.length > 0) {
    issues.push(`未暂存的文档/配置变更（可能需要一起提交）: ${unstagedDocs.join(", ")}`);
  }

  const stagedTouchesAutomation = staged.some(
    (file) =>
      file.startsWith("scripts/") ||
      file.startsWith(".claude/") ||
      file.startsWith(".pi/") ||
      file.startsWith(".agents/"),
  );
  if (stagedTouchesAutomation && !staged.includes("CLAUDE.md")) {
    issues.push("修改了 scripts/、.claude/、.agents/ 或 .pi/ 但未更新 CLAUDE.md — 检查项目结构/命令/自动化是否需要同步");
  }

  const stagedDocs = staged.filter((file) => /^docs\/[^/]+\.md$/.test(file) && !file.endsWith("TEMPLATE.md"));
  if (stagedDocs.length > 0 && !staged.includes("agents.yaml")) {
    issues.push("新增/修改了分析文档但未更新 agents.yaml — 检查 status 是否需要变更");
  }

  const changedDemoAgents = new Set(
    staged
      .map((file) => file.match(/^demos\/([^/]+)\/[^/]+\//)?.[1])
      .filter((value): value is string => Boolean(value)),
  );
  for (const agent of changedDemoAgents) {
    if (!staged.includes(`demos/${agent}/README.md`)) {
      issues.push(`修改了 demos/${agent}/ 下的 demo 但未更新 demos/${agent}/README.md overview`);
    }
  }

  if (stagedDocs.length > 0 && staged.includes("agents.yaml")) {
    const diff = await pi.exec("git", ["diff", "--cached", "--", "agents.yaml"], {
      cwd: repoRoot,
      timeout: 10_000,
    });
    const agentsYamlDiff = diff.stdout + diff.stderr;
    if (!agentsYamlDiff.includes("analyzed_commit")) {
      for (const docChange of stagedDocs) {
        const agentName = path.basename(docChange, ".md");
        issues.push(
          `暂存了 docs/${agentName}.md 和 agents.yaml，但 agents.yaml 中未更新 analyzed_commit — 检查是否需要 stamp commit`,
        );
      }
    }
  }

  if (staged.includes("README.md") && unstaged.includes("README.en.md")) {
    issues.push("暂存了 README.md 但 README.en.md 有未暂存变更 — 多语言 README 需同步");
  }

  return issues;
}

async function runPythonSyntaxCheck(pi: ExtensionAPI, cwd: string, filePath: string): Promise<string | undefined> {
  const result = await pi.exec("python3", ["-m", "py_compile", filePath], {
    cwd,
    timeout: 30_000,
  });
  if (result.code === 0) return undefined;
  return truncateText(result.stderr || result.stdout || `python3 -m py_compile ${filePath} failed`);
}

async function runTypeScriptSyntaxCheck(pi: ExtensionAPI, absolutePath: string): Promise<string | undefined> {
  const demoDir = path.dirname(absolutePath);
  const tsconfigPath = path.join(demoDir, "tsconfig.json");
  if (!existsSync(tsconfigPath)) return undefined;

  const result = await pi.exec("npx", ["tsc", "--noEmit"], {
    cwd: demoDir,
    timeout: 60_000,
  });
  if (result.code === 0) return undefined;
  return truncateText(result.stderr || result.stdout || `npx tsc --noEmit failed in ${demoDir}`);
}

async function runRustSyntaxCheck(pi: ExtensionAPI, absolutePath: string): Promise<string | undefined> {
  let cargoDir = path.dirname(absolutePath);
  if (existsSync(path.join(cargoDir, "..", "Cargo.toml"))) {
    cargoDir = path.resolve(cargoDir, "..");
  }
  if (!existsSync(path.join(cargoDir, "Cargo.toml"))) return undefined;

  const result = await pi.exec("cargo", ["check"], {
    cwd: cargoDir,
    timeout: 120_000,
  });
  if (result.code === 0) return undefined;
  return truncateText(result.stderr || result.stdout || `cargo check failed in ${cargoDir}`);
}

function validateAgentsYamlFile(absolutePath: string): string | undefined {
  const content = readFileSync(absolutePath, "utf8");
  let errors = "";

  if (!/^agents:/m.test(content)) {
    errors += "Missing top-level 'agents:' key. ";
  }

  const agentCount = (content.match(/-\s*name:/g) ?? []).length;
  const repoCount = (content.match(/\brepo:/g) ?? []).length;
  const statusCount = (content.match(/\bstatus:/g) ?? []).length;

  if (agentCount === 0) {
    errors += "No agents found. ";
  } else if (repoCount < agentCount) {
    errors += "Some agents missing 'repo:' field. ";
  } else if (statusCount < agentCount) {
    errors += "Some agents missing 'status:' field. ";
  }

  const statusLines = content.match(/^\s*status:\s*.+$/gm) ?? [];
  if (statusLines.some((line) => !/^\s*status:\s*(pending|in-progress|done)\s*$/i.test(line))) {
    errors += "Unknown status values found. ";
  }

  const commitLines = content.match(/^\s*analyzed_commit:\s*.+$/gm) ?? [];
  if (commitLines.some((line) => !/^\s*analyzed_commit:\s*[0-9a-f]{7,40}\s*$/i.test(line))) {
    errors += "Invalid analyzed_commit format (must be 7-40 hex chars). ";
  }

  const typeLines = content.match(/^\s*type:\s*.+$/gm) ?? [];
  if (typeLines.some((line) => !/^\s*type:\s*(coding-agent|agent-platform)\s*$/i.test(line))) {
    errors += "Unknown type values (must be coding-agent or agent-platform). ";
  }

  return errors.trim() || undefined;
}

function isDemoSourcePath(relativePath: string): boolean {
  if (!relativePath.startsWith("demos/")) return false;
  return /\.(py|ts|rs)$/.test(relativePath);
}

export default function claudeCompat(pi: ExtensionAPI) {
  let lastProjectStatus: ProjectStatus | undefined;

  async function refreshStatus(cwd: string, notifyUser: boolean, setWidget: boolean, ui?: {
    notify: (message: string, level: "info" | "warning" | "error") => void;
    setWidget: (id: string, value: string[] | undefined) => void;
  }) {
    lastProjectStatus = await buildProjectStatus(pi, cwd);
    if (!lastProjectStatus) return;

    if (setWidget && ui) {
      ui.setWidget("claude-compat-status", lastProjectStatus.widgetLines);
    }
    if (notifyUser && ui) {
      ui.notify(truncateText(lastProjectStatus.summary, 500), "info");
    }
  }

  pi.on("session_start", async (_event, ctx) => {
    await refreshStatus(ctx.cwd, true, ctx.hasUI, ctx.hasUI
      ? {
          notify: (message, level) => ctx.ui.notify(message, level),
          setWidget: (id, value) => ctx.ui.setWidget(id, value),
        }
      : undefined);
  });

  pi.on("before_agent_start", async (event, ctx) => {
    const status = (await buildProjectStatus(pi, ctx.cwd)) ?? lastProjectStatus;
    if (!status) return undefined;

    return {
      systemPrompt:
        event.systemPrompt +
        `\n\n## Project Status Snapshot\n${status.summary}\n\nUse this snapshot as current repository workflow context.`,
    };
  });

  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName !== "bash") return undefined;

    const command = typeof event.input.command === "string" ? event.input.command : "";
    if (!command.includes("git commit")) return undefined;

    const isCompoundCommand = command.includes("&&") || command.includes(";") || command.includes("||") || command.includes("\n");
    if (isCompoundCommand) {
      if (ctx.hasUI) {
        ctx.ui.notify("检测到复合 git 提交命令，跳过执行前拦截，交由实际 git hooks 校验。", "warning");
      }
      return undefined;
    }

    const issues = await runPreCommitChecks(pi, ctx.cwd);
    if (issues.length === 0) return undefined;

    const message = ["提交前检查发现以下可能遗漏：", ...issues.map((issue) => `- ${issue}`), "请确认是否需要处理后再提交。"].join("\n");
    if (ctx.hasUI) {
      ctx.ui.notify(truncateText(message, 700), "warning");
    }
    return { block: true, reason: message };
  });

  pi.on("tool_result", async (event, ctx) => {
    if (event.isError) return;
    if (event.toolName !== "edit" && event.toolName !== "write") return;

    const input = event.input as { path?: unknown };
    if (typeof input?.path !== "string") return;

    const absolutePath = path.resolve(ctx.cwd, input.path);
    const relativePath = path.relative(ctx.cwd, absolutePath).split(path.sep).join("/");

    if (relativePath === "agents.yaml") {
      try {
        const validationError = validateAgentsYamlFile(absolutePath);
        if (ctx.hasUI) {
          if (validationError) {
            ctx.ui.notify(`agents.yaml validation FAILED: ${truncateText(validationError)}`, "error");
          } else {
            const statuses = parseAgentsYamlStatuses(absolutePath);
            ctx.ui.notify(`agents.yaml OK: ${statuses.length} agents validated`, "info");
          }
        }
      } catch (error) {
        if (ctx.hasUI) {
          ctx.ui.notify(`agents.yaml validation FAILED: ${truncateText(String(error))}`, "error");
        }
      }
      await refreshStatus(ctx.cwd, false, ctx.hasUI, ctx.hasUI
        ? {
            notify: (message, level) => ctx.ui.notify(message, level),
            setWidget: (id, value) => ctx.ui.setWidget(id, value),
          }
        : undefined);
      return;
    }

    if (!isDemoSourcePath(relativePath)) return;

    const extension = path.extname(relativePath);
    let errorMessage: string | undefined;

    if (extension === ".py") {
      errorMessage = await runPythonSyntaxCheck(pi, ctx.cwd, relativePath);
    } else if (extension === ".ts") {
      errorMessage = await runTypeScriptSyntaxCheck(pi, absolutePath);
    } else if (extension === ".rs") {
      errorMessage = await runRustSyntaxCheck(pi, absolutePath);
    }

    if (errorMessage && ctx.hasUI) {
      ctx.ui.notify(`Syntax check failed for ${relativePath}: ${errorMessage}`, "error");
    }

    await refreshStatus(ctx.cwd, false, ctx.hasUI, ctx.hasUI
      ? {
          notify: (message, level) => ctx.ui.notify(message, level),
          setWidget: (id, value) => ctx.ui.setWidget(id, value),
        }
      : undefined);
  });
}
