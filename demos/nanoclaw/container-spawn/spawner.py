"""容器启动与 IPC — NanoClaw Container Runner 核心

基于 src/container-runner.ts (649 行)。

核心机制:
  1. Volume Mount 构建: main/non-main 差异化挂载
  2. 容器启动: subprocess spawn + stdin JSON 注入 (secrets 仅通过 stdin 传递)
  3. 哨兵标记流式解析: OUTPUT_START/END marker 从 stdout 提取 JSON
  4. 超时管理: hard timeout + idle timeout + activity reset
  5. 错误处理: 退出码检查、输出解析失败、超时分类
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# Sentinel markers (must match agent-runner)
OUTPUT_START = "---NANOCLAW_OUTPUT_START---"
OUTPUT_END = "---NANOCLAW_OUTPUT_END---"


@dataclass
class VolumeMount:
    host_path: str
    container_path: str
    readonly: bool = False


@dataclass
class ContainerInput:
    prompt: str
    group_folder: str
    chat_jid: str
    is_main: bool
    session_id: str | None = None
    assistant_name: str = "Andy"


@dataclass
class ContainerOutput:
    status: str  # 'success' | 'error'
    result: str | None = None
    new_session_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Sentinel stream parser
# ---------------------------------------------------------------------------

class SentinelParser:
    """从混合了日志的 stdout 流中提取哨兵标记之间的 JSON。

    NanoClaw 的容器通过 stdout 输出结果，但 Claude SDK 也会往 stdout 写日志。
    哨兵标记让 host 能可靠地区分结果 JSON 和日志噪声。

    协议:
      ---NANOCLAW_OUTPUT_START---
      {"status":"success","result":"...","newSessionId":"..."}
      ---NANOCLAW_OUTPUT_END---
    """

    def __init__(self) -> None:
        self._buffer = ""
        self.outputs: list[ContainerOutput] = []

    def feed(self, chunk: str) -> list[ContainerOutput]:
        """Feed a chunk of stdout data. Returns newly parsed outputs."""
        self._buffer += chunk
        new_outputs: list[ContainerOutput] = []

        while True:
            start_idx = self._buffer.find(OUTPUT_START)
            if start_idx == -1:
                break
            end_idx = self._buffer.find(OUTPUT_END, start_idx)
            if end_idx == -1:
                break  # Incomplete pair, wait for more data

            json_str = self._buffer[start_idx + len(OUTPUT_START):end_idx].strip()
            self._buffer = self._buffer[end_idx + len(OUTPUT_END):]

            try:
                data = json.loads(json_str)
                output = ContainerOutput(
                    status=data.get("status", "error"),
                    result=data.get("result"),
                    new_session_id=data.get("newSessionId"),
                    error=data.get("error"),
                )
                self.outputs.append(output)
                new_outputs.append(output)
            except json.JSONDecodeError:
                new_outputs.append(ContainerOutput(
                    status="error", error=f"JSON parse error: {json_str[:100]}"
                ))

        return new_outputs

    def parse_legacy(self, stdout: str) -> ContainerOutput:
        """Legacy mode: parse last marker pair or last line (backwards compat)."""
        start_idx = stdout.rfind(OUTPUT_START)
        end_idx = stdout.rfind(OUTPUT_END)

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = stdout[start_idx + len(OUTPUT_START):end_idx].strip()
        else:
            # Fallback: last non-empty line
            lines = stdout.strip().split("\n")
            json_str = lines[-1] if lines else ""

        try:
            data = json.loads(json_str)
            return ContainerOutput(
                status=data.get("status", "error"),
                result=data.get("result"),
                new_session_id=data.get("newSessionId"),
            )
        except json.JSONDecodeError:
            return ContainerOutput(status="error", error="Failed to parse output")


# ---------------------------------------------------------------------------
# Volume mount builder
# ---------------------------------------------------------------------------

def build_volume_mounts(
    group_folder: str,
    is_main: bool,
    *,
    project_root: str = ".",
    groups_dir: str = "groups",
    data_dir: str = "data",
) -> list[VolumeMount]:
    """构建容器挂载列表，复现 container-runner.ts:buildVolumeMounts。

    Main 组群: project_root(ro) + group(rw) + session(rw) + ipc(rw)
    非 Main:  group(rw) + global(ro) + session(rw) + ipc(rw)
    """
    mounts: list[VolumeMount] = []
    group_dir = os.path.join(groups_dir, group_folder)

    if is_main:
        mounts.append(VolumeMount(project_root, "/workspace/project", readonly=True))
        mounts.append(VolumeMount(group_dir, "/workspace/group", readonly=False))
    else:
        mounts.append(VolumeMount(group_dir, "/workspace/group", readonly=False))
        global_dir = os.path.join(groups_dir, "global")
        if os.path.exists(global_dir):
            mounts.append(VolumeMount(global_dir, "/workspace/global", readonly=True))

    # Per-group session directory
    session_dir = os.path.join(data_dir, "sessions", group_folder, ".claude")
    mounts.append(VolumeMount(session_dir, "/home/node/.claude", readonly=False))

    # Per-group IPC namespace
    ipc_dir = os.path.join(data_dir, "ipc", group_folder)
    mounts.append(VolumeMount(ipc_dir, "/workspace/ipc", readonly=False))

    return mounts


# ---------------------------------------------------------------------------
# Container spawner (uses subprocess to simulate Docker)
# ---------------------------------------------------------------------------

def spawn_mock_agent(
    script_content: str,
    container_input: ContainerInput,
    timeout_s: float = 10.0,
    on_output: Callable[[ContainerOutput], None] | None = None,
) -> ContainerOutput:
    """启动 mock agent 脚本（模拟 Docker 容器），演示完整的容器生命周期。

    在原实现中:
    - spawn(CONTAINER_RUNTIME_BIN, containerArgs, {stdio: ['pipe', 'pipe', 'pipe']})
    - container.stdin.write(JSON.stringify(input))
    - container.stdout.on('data', ...) → sentinel parser
    - container.on('close', ...) → result handling

    Demo 用 Python subprocess 模拟。
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script_content)
        script_path = f.name

    try:
        proc = subprocess.Popen(
            ["python3", script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Pass input via stdin (secrets stay in-memory, never on disk)
        stdin_json = json.dumps({
            "prompt": container_input.prompt,
            "sessionId": container_input.session_id,
            "groupFolder": container_input.group_folder,
            "chatJid": container_input.chat_jid,
            "isMain": container_input.is_main,
        })

        # Use communicate() with timeout for reliable timeout handling.
        # In the original TS implementation, stdin is written then ended,
        # and stdout is event-driven (non-blocking). Python needs communicate().
        try:
            stdout_acc, stderr = proc.communicate(
                input=stdin_json, timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return ContainerOutput(status="error", error=f"Timeout after {timeout_s}s")

        # Parse streamed outputs from accumulated stdout
        parser = SentinelParser()
        new_outputs = parser.feed(stdout_acc)
        if on_output:
            for out in new_outputs:
                on_output(out)

        if proc.returncode != 0:
            return ContainerOutput(
                status="error",
                error=f"Exit code {proc.returncode}: {stderr[-200:]}"
            )

        # If streaming mode found outputs, return last session
        if parser.outputs:
            last = parser.outputs[-1]
            return ContainerOutput(
                status="success", result=None,
                new_session_id=last.new_session_id,
            )

        # Legacy fallback
        return parser.parse_legacy(stdout_acc)

    finally:
        os.unlink(script_path)
