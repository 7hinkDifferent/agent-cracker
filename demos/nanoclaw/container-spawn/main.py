"""NanoClaw 容器启动与 IPC — Demo

演示 container-runner 的核心机制：
  1. Volume mount 构建（main vs non-main 差异）
  2. 哨兵标记流式解析（从混合日志中提取 JSON）
  3. 完整容器生命周期（spawn → stdin → stdout parse → result）
  4. 超时与错误处理
  5. Legacy 回退解析

运行: uv run python main.py
"""

from __future__ import annotations

import json
import os
import textwrap

from spawner import (
    ContainerInput,
    ContainerOutput,
    SentinelParser,
    VolumeMount,
    build_volume_mounts,
    spawn_mock_agent,
    OUTPUT_START,
    OUTPUT_END,
)


# ---------------------------------------------------------------------------
# Demo 1: Volume mount 构建 — main vs non-main
# ---------------------------------------------------------------------------

def demo_volume_mounts():
    print("=" * 60)
    print("Demo 1: Volume Mount 构建 — main vs non-main 差异")
    print("=" * 60)

    # Create minimal directory structure
    os.makedirs("groups/global", exist_ok=True)

    print("\n  Main 组群 mounts:")
    main_mounts = build_volume_mounts("main", is_main=True)
    for m in main_mounts:
        ro = " (ro)" if m.readonly else ""
        print(f"    {m.host_path} → {m.container_path}{ro}")

    print("\n  非 Main 组群 mounts:")
    team_mounts = build_volume_mounts("team", is_main=False)
    for m in team_mounts:
        ro = " (ro)" if m.readonly else ""
        print(f"    {m.host_path} → {m.container_path}{ro}")

    print(f"\n  Main 有项目根目录只读挂载: {any(m.container_path == '/workspace/project' for m in main_mounts)}")
    print(f"  Non-main 有全局记忆只读挂载: {any(m.container_path == '/workspace/global' for m in team_mounts)}")

    # Cleanup
    os.rmdir("groups/global")
    os.rmdir("groups")
    print()


# ---------------------------------------------------------------------------
# Demo 2: 哨兵标记流式解析
# ---------------------------------------------------------------------------

def demo_sentinel_parsing():
    print("=" * 60)
    print("Demo 2: 哨兵标记流式解析 — 从混合日志中提取 JSON")
    print("=" * 60)

    parser = SentinelParser()

    # Simulate chunked stdout with logs mixed in
    chunks = [
        "[DEBUG] Claude SDK initializing...\n",
        "[DEBUG] Loading tools...\n",
        f"{OUTPUT_START}\n",
        '{"status":"success","result":"天气查询结果: 北京 25°C","new',
        f'SessionId":"sess-abc123"}}\n{OUTPUT_END}\n',
        "[DEBUG] Session saved\n",
        f"{OUTPUT_START}\n",
        '{"status":"success","result":null,"newSessionId":"sess-abc123"}\n',
        f"{OUTPUT_END}\n",
    ]

    print("\n  逐 chunk 输入 (模拟流式读取):")
    for i, chunk in enumerate(chunks):
        preview = chunk.strip()[:50]
        outputs = parser.feed(chunk)
        status = f"→ 解析出 {len(outputs)} 个输出" if outputs else ""
        print(f"    chunk {i}: {preview!r:52s} {status}")
        for out in outputs:
            print(f"      result={str(out.result)[:40]}, session={out.new_session_id}")

    print(f"\n  总计解析出 {len(parser.outputs)} 个输出")
    print()


# ---------------------------------------------------------------------------
# Demo 3: Legacy 回退解析
# ---------------------------------------------------------------------------

def demo_legacy_parsing():
    print("=" * 60)
    print("Demo 3: Legacy 回退解析 — 无标记时解析最后一行")
    print("=" * 60)

    parser = SentinelParser()

    # With markers
    stdout_with = (
        "[LOG] ...\n"
        f"{OUTPUT_START}\n"
        '{"status":"success","result":"OK"}\n'
        f"{OUTPUT_END}\n"
    )
    result1 = parser.parse_legacy(stdout_with)
    print(f"\n  有标记: status={result1.status}, result={result1.result}")

    # Without markers (backwards compat)
    stdout_without = (
        "[LOG] ...\n"
        '{"status":"success","result":"fallback"}\n'
    )
    result2 = parser.parse_legacy(stdout_without)
    print(f"  无标记: status={result2.status}, result={result2.result}")

    # Malformed
    result3 = parser.parse_legacy("not json at all\n")
    print(f"  异常:   status={result3.status}, error={result3.error}")
    print()


# ---------------------------------------------------------------------------
# Demo 4: 完整容器生命周期
# ---------------------------------------------------------------------------

def demo_full_lifecycle():
    print("=" * 60)
    print("Demo 4: 完整容器生命周期 — spawn → stdin → parse → result")
    print("=" * 60)

    # Mock agent script that reads stdin and writes sentinel-wrapped output
    agent_script = textwrap.dedent(f"""\
        import json, sys
        input_data = json.loads(sys.stdin.read())
        prompt = input_data["prompt"]
        # Simulate some log output
        print("[DEBUG] Agent starting...", file=sys.stderr)
        print("[LOG] Processing prompt...")
        # Write result with sentinel markers
        result = json.dumps({{
            "status": "success",
            "result": f"处理完成: {{prompt[:30]}}",
            "newSessionId": "sess-demo-001",
        }})
        print("{OUTPUT_START}")
        print(result)
        print("{OUTPUT_END}")
    """)

    streamed: list[ContainerOutput] = []

    def on_output(out: ContainerOutput):
        streamed.append(out)
        print(f"    [streaming] status={out.status}, result={str(out.result)[:40]}")

    input_data = ContainerInput(
        prompt="帮我查一下明天的天气",
        group_folder="main",
        chat_jid="main@g.us",
        is_main=True,
    )

    print(f"\n  输入: prompt={input_data.prompt!r}")
    result = spawn_mock_agent(agent_script, input_data, on_output=on_output)
    print(f"  最终结果: status={result.status}, session={result.new_session_id}")
    print(f"  流式输出数: {len(streamed)}")
    print()


# ---------------------------------------------------------------------------
# Demo 5: 超时处理
# ---------------------------------------------------------------------------

def demo_timeout():
    print("=" * 60)
    print("Demo 5: 超时处理 — 容器超时后被 kill")
    print("=" * 60)

    slow_script = textwrap.dedent("""\
        import time, sys
        sys.stdin.read()
        time.sleep(10)  # Hang forever
    """)

    input_data = ContainerInput(
        prompt="test", group_folder="test", chat_jid="test@g.us", is_main=False,
    )

    print(f"\n  启动慢速 agent (timeout=1s)...")
    result = spawn_mock_agent(slow_script, input_data, timeout_s=1.0)
    print(f"  结果: status={result.status}, error={result.error}")
    print()


# ---------------------------------------------------------------------------
# Demo 6: 非零退出码
# ---------------------------------------------------------------------------

def demo_error_exit():
    print("=" * 60)
    print("Demo 6: 非零退出码 — 容器异常退出")
    print("=" * 60)

    crash_script = textwrap.dedent("""\
        import sys
        sys.stdin.read()
        print("Fatal: out of memory", file=sys.stderr)
        sys.exit(1)
    """)

    input_data = ContainerInput(
        prompt="test", group_folder="test", chat_jid="test@g.us", is_main=False,
    )

    result = spawn_mock_agent(crash_script, input_data)
    print(f"\n  结果: status={result.status}")
    print(f"  错误: {result.error}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("NanoClaw 容器启动与 IPC — 机制 Demo\n")
    demo_volume_mounts()
    demo_sentinel_parsing()
    demo_legacy_parsing()
    demo_full_lifecycle()
    demo_timeout()
    demo_error_exit()
    print("✓ 所有 demo 完成")
