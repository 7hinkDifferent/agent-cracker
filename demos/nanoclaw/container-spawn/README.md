# container-spawn — 容器启动与 IPC

## 目标

复现 NanoClaw 的容器生命周期管理：Volume mount 构建 → 子进程启动 → stdin JSON 注入 → 哨兵标记流式输出解析 → 超时/错误处理。

## MVP 角色

Container Runner 是 Host 层与 Container 层的桥梁。它将消息"翻译"为容器输入，并从容器输出中可靠地提取结果 JSON。

## 原理

```
Host                                Container (Docker)
  │                                     │
  │ 1. buildVolumeMounts()              │
  │    main: project(ro)+group(rw)      │
  │    other: group(rw)+global(ro)      │
  │                                     │
  │ 2. spawn(docker, args)              │
  │──────stdin JSON──────────────────→  │ 读取 input
  │    {prompt, sessionId, secrets}      │
  │                                     │ 处理...
  │  ←───stdout (mixed logs + result)───│
  │    [LOG] ...                        │
  │    ---NANOCLAW_OUTPUT_START---      │
  │    {"status":"success",...}          │
  │    ---NANOCLAW_OUTPUT_END---        │
  │                                     │
  │ 3. SentinelParser.feed(chunk)       │
  │    提取 START..END 之间的 JSON       │
  │                                     │
  │ 4. on('close') → 结果处理            │
  │    code!=0 → error                  │
  │    timeout → kill + error            │
  │    success → session update          │
```

**哨兵标记协议**: 容器输出的 stdout 混合了 SDK 日志和结果 JSON。通过唯一标记对 `---NANOCLAW_OUTPUT_START---` / `---NANOCLAW_OUTPUT_END---` 包裹 JSON，host 能可靠地从噪声中提取结果。

**Secrets 传递**: API 密钥仅通过 stdin JSON 传递，不写入磁盘或挂载为文件，避免泄露。

## 运行

```bash
uv run python main.py
```

无外部依赖，使用 `subprocess` 模拟 Docker 容器。

## 文件结构

```
container-spawn/
├── README.md       # 本文件
├── main.py         # Demo 入口（6 个演示场景）
└── spawner.py      # 可复用模块: SentinelParser + build_volume_mounts + spawn_mock_agent
```

## 关键代码解读

### 哨兵标记流式解析（spawner.py）

```python
class SentinelParser:
    def feed(self, chunk: str) -> list[ContainerOutput]:
        self._buffer += chunk
        while True:
            start_idx = self._buffer.find(OUTPUT_START)
            end_idx = self._buffer.find(OUTPUT_END, start_idx)
            if start_idx == -1 or end_idx == -1:
                break  # 不完整的标记对，等更多数据
            json_str = self._buffer[start_idx + len(OUTPUT_START):end_idx].strip()
            self._buffer = self._buffer[end_idx + len(OUTPUT_END):]
            # 解析 JSON...
```

缓冲区策略：未匹配完成的数据保留在 buffer 中，等下一个 chunk 到达时继续匹配。

### Volume Mount 差异（spawner.py）

```python
if is_main:
    mounts.append(VolumeMount(project_root, "/workspace/project", readonly=True))
    mounts.append(VolumeMount(group_dir, "/workspace/group", readonly=False))
else:
    mounts.append(VolumeMount(group_dir, "/workspace/group", readonly=False))
    mounts.append(VolumeMount(global_dir, "/workspace/global", readonly=True))
```

Main 组群获得项目根目录（只读），非 main 组群获得全局记忆目录（只读）。

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 容器运行时 | Docker (`spawn("docker", args)`) | Python `subprocess`（mock 脚本） |
| 挂载安全 | `validateAdditionalMounts()` 外部 allowlist | 未实现（见 mount-security demo） |
| Session 目录 | 自动创建 `.claude/settings.json` | 未创建实际目录 |
| Skills 同步 | `container/skills/` → 每组 `.claude/skills/` | 未实现 |
| 流式解析 | 真正的流式（stdout on data） | `communicate()` 后批量解析 |
| 日志存储 | 写入 `groups/{name}/logs/` | 无日志文件 |
| 超时机制 | `setTimeout` + `docker stop` + SIGKILL | `communicate(timeout=)` |

## 相关文档

- 分析文档: [docs/nanoclaw.md — D2 Agent Loop](../../docs/nanoclaw.md#2-agent-loop主循环机制)
- 安全模型: [docs/nanoclaw.md — D11 安全模型](../../docs/nanoclaw.md#11-安全模型与自治-平台维度)
- 原始源码: `projects/nanoclaw/src/container-runner.ts` (649 行)
- 容器运行时: `projects/nanoclaw/src/container-runtime.ts` (76 行)
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
