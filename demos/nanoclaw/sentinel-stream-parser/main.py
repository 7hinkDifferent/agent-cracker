"""流式哨兵标记解析 — Demo

演示 NanoClaw 的流式哨兵标记解析机制：
  1. 基本解析 — 完整标记对在单个 chunk 中
  2. 跨 chunk 边界 — START 和 END 分属不同 chunk
  3. 多输出提取 — 单 chunk 含多个 START/END 对
  4. 混合内容 — SDK 日志与标记对交错
  5. 异常处理 — 缺失 END、非法 JSON、嵌套标记

运行: uv run python main.py
"""

from __future__ import annotations

import json

from parser import (
    EventType,
    StreamingSentinelParser,
    OUTPUT_START,
    OUTPUT_END,
)


def _make_output_block(data: dict) -> str:
    """生成一个完整的哨兵标记包裹的 JSON 块"""
    return f"{OUTPUT_START}\n{json.dumps(data)}\n{OUTPUT_END}\n"


def _print_events(events: list, indent: str = "    ") -> None:
    """格式化打印解析事件列表"""
    if not events:
        print(f"{indent}(无新事件)")
        return
    for ev in events:
        if ev.event_type == EventType.OUTPUT:
            out = ev.output
            result_preview = str(out.result)[:40] if out.result else "null"
            print(f"{indent}[OUTPUT] status={out.status}, result={result_preview}")
        elif ev.event_type == EventType.ERROR:
            print(f"{indent}[ERROR]  {ev.error_message}")


# ---------------------------------------------------------------------------
# Demo 1: 基本解析 — 完整标记对在单个 chunk 中
# ---------------------------------------------------------------------------

def demo_basic_parsing():
    print("=" * 64)
    print("Demo 1: 基本解析 — 完整标记对在单个 chunk 中")
    print("=" * 64)
    print()
    print("  场景: 单个 chunk 包含完整的 START...JSON...END")
    print("  对应原实现: parseBuffer 一次性包含完整标记对")
    print()

    parser = StreamingSentinelParser()
    payload = {"status": "success", "result": "北京今天25°C，晴", "newSessionId": "sess-001"}
    chunk = _make_output_block(payload)

    print(f"  输入 chunk ({len(chunk)} bytes):")
    for line in chunk.strip().split("\n"):
        print(f"    | {line}")
    print()

    events = parser.feed(chunk)
    print(f"  解析结果 ({len(events)} 个事件):")
    _print_events(events)

    assert len(events) == 1
    assert events[0].event_type == EventType.OUTPUT
    assert events[0].output.result == "北京今天25°C，晴"
    assert events[0].output.new_session_id == "sess-001"
    assert parser.parsed_count == 1

    print(f"\n  parser.parsed_count = {parser.parsed_count}")
    print(f"  parser.buffer_size  = {parser.buffer_size}")
    print()


# ---------------------------------------------------------------------------
# Demo 2: 跨 chunk 边界 — START 和 END 分属不同 chunk
# ---------------------------------------------------------------------------

def demo_chunk_boundary():
    print("=" * 64)
    print("Demo 2: 跨 chunk 边界 — 标记分属不同 chunk")
    print("=" * 64)
    print()
    print("  场景: 容器输出被 OS 按任意边界拆分为多个 chunk")
    print("  关键: buffer 累积机制确保跨 chunk 标记仍能匹配")
    print()

    parser = StreamingSentinelParser()
    full_json = json.dumps({"status": "success", "result": "跨 chunk 测试"})

    # 将一个完整输出拆成 4 个 chunk，模拟网络/OS 拆分
    chunks = [
        "[DEBUG] SDK loading...\n---NANOCLAW",          # 不完整 START
        "_OUTPUT_START---\n",                            # START 结束
        f'{full_json}\n---NANOCLAW_OUTPU',               # JSON + 不完整 END
        "T_END---\n[DEBUG] done\n",                      # END 结束 + 日志
    ]

    print("  逐 chunk 输入:")
    all_events = []
    for i, chunk in enumerate(chunks):
        preview = chunk.replace("\n", "\\n")
        if len(preview) > 55:
            preview = preview[:52] + "..."
        events = parser.feed(chunk)
        status = f"-> {len(events)} 个事件" if events else "-> 等待更多数据"
        print(f"    chunk {i}: {preview!r:57s} {status}")
        all_events.extend(events)
        _print_events(events, indent="      ")

    assert len(all_events) == 1
    assert all_events[0].output.result == "跨 chunk 测试"
    assert parser.parsed_count == 1

    # 调用 flush 获取残留内容
    remaining = parser.flush()
    print(f"\n  flush() 残留: {remaining.strip()!r}")
    print(f"  parser.parsed_count = {parser.parsed_count}")
    print()


# ---------------------------------------------------------------------------
# Demo 3: 多输出提取 — 单 chunk 含多个 START/END 对
# ---------------------------------------------------------------------------

def demo_multiple_outputs():
    print("=" * 64)
    print("Demo 3: 多输出提取 — 单 chunk 含多个 START/END 对")
    print("=" * 64)
    print()
    print("  场景: 容器快速输出多个结果，OS 将它们合并到同一个 chunk")
    print("  对应原实现: while 循环反复搜索直到无完整标记对")
    print()

    parser = StreamingSentinelParser()

    output1 = {"status": "success", "result": "第一个结果", "newSessionId": "sess-a"}
    output2 = {"status": "success", "result": None, "newSessionId": "sess-a"}

    # 两个输出合并为一个 chunk
    chunk = (
        "[LOG] processing query 1...\n"
        + _make_output_block(output1)
        + "[LOG] processing query 2...\n"
        + _make_output_block(output2)
    )

    print(f"  输入 chunk ({len(chunk)} bytes, 含 2 个标记对):")
    for line in chunk.strip().split("\n"):
        tag = ""
        if OUTPUT_START in line:
            tag = "  <-- START"
        elif OUTPUT_END in line:
            tag = "  <-- END"
        print(f"    | {line}{tag}")
    print()

    events = parser.feed(chunk)
    print(f"  解析结果 ({len(events)} 个事件):")
    _print_events(events)

    assert len(events) == 2
    assert events[0].output.result == "第一个结果"
    assert events[1].output.result is None
    assert parser.parsed_count == 2

    print(f"\n  parser.parsed_count = {parser.parsed_count}")
    print()


# ---------------------------------------------------------------------------
# Demo 4: 混合内容 — SDK 日志与标记对交错
# ---------------------------------------------------------------------------

def demo_mixed_content():
    print("=" * 64)
    print("Demo 4: 混合内容 — SDK 日志与标记对交错")
    print("=" * 64)
    print()
    print("  场景: Claude SDK 持续写入调试日志，结果 JSON 穿插其中")
    print("  关键: 日志行被丢弃，只有标记包裹的 JSON 被提取")
    print()

    parser = StreamingSentinelParser()

    # 模拟多个 chunk 的真实流
    chunks = [
        "[2026-02-25T10:00:01] INFO  claude-sdk: Initializing session\n",
        "[2026-02-25T10:00:01] DEBUG claude-sdk: Loading tools from MCP\n",
        "[2026-02-25T10:00:02] INFO  claude-sdk: Processing user message\n",
        "[2026-02-25T10:00:03] DEBUG claude-sdk: Tool call: send_message\n",
        (
            _make_output_block({"status": "success", "result": "已发送消息给运营群"})
        ),
        "[2026-02-25T10:00:04] DEBUG claude-sdk: Continuing conversation\n",
        "[2026-02-25T10:00:05] INFO  claude-sdk: Final response ready\n",
        (
            _make_output_block({"status": "success", "result": None, "newSessionId": "sess-final"})
        ),
        "[2026-02-25T10:00:05] INFO  claude-sdk: Session saved\n",
    ]

    print("  逐 chunk 输入 (模拟真实 stdout 流):")
    total_events = []
    for i, chunk in enumerate(chunks):
        preview = chunk.strip()[:60]
        events = parser.feed(chunk)
        marker = ""
        if events:
            marker = f" -> {len(events)} 个输出"
        print(f"    [{i:2d}] {preview!r:62s}{marker}")
        total_events.extend(events)

    print(f"\n  提取的输出 ({len(total_events)} 个):")
    _print_events(total_events)

    remaining = parser.flush()
    print(f"\n  残留日志: {remaining.strip()!r}" if remaining.strip() else "\n  残留日志: (空)")

    assert len(total_events) == 2
    assert total_events[0].output.result == "已发送消息给运营群"
    assert total_events[1].output.new_session_id == "sess-final"
    assert parser.parsed_count == 2
    assert parser.error_count == 0

    print(f"  parser.parsed_count = {parser.parsed_count}")
    print(f"  parser.error_count  = {parser.error_count}")
    print()


# ---------------------------------------------------------------------------
# Demo 5: 异常处理 — 缺失 END、非法 JSON、嵌套标记
# ---------------------------------------------------------------------------

def demo_malformed():
    print("=" * 64)
    print("Demo 5: 异常处理 — 缺失 END / 非法 JSON / 嵌套标记")
    print("=" * 64)

    # --- 5a: 缺失 END 标记 ---
    print("\n  5a: 缺失 END 标记")
    print("  场景: 容器崩溃，只写了 START 没写 END")
    print()

    parser_a = StreamingSentinelParser()
    chunk_a = f"[LOG] starting...\n{OUTPUT_START}\n" + '{"status":"success","result":"incomplete"}\n'
    events_a = parser_a.feed(chunk_a)
    print(f"    feed() 返回 {len(events_a)} 个事件 (START 未闭合，等待更多数据)")
    print(f"    buffer_size = {parser_a.buffer_size}")

    # 模拟容器关闭，flush 获取残留
    remaining_a = parser_a.flush()
    print(f"    flush() 残留: {remaining_a.strip()!r}")
    print(f"    -> 调用方可检测到 flush 包含未闭合标记，视为错误")

    assert len(events_a) == 0
    assert OUTPUT_START in remaining_a

    # --- 5b: 非法 JSON ---
    print("\n  5b: 非法 JSON")
    print("  场景: 标记对内的 JSON 格式错误")
    print()

    parser_b = StreamingSentinelParser()
    chunk_b = f"{OUTPUT_START}\nnot-valid-json{{broken\n{OUTPUT_END}\n"
    events_b = parser_b.feed(chunk_b)
    print(f"    feed() 返回 {len(events_b)} 个事件:")
    _print_events(events_b)

    assert len(events_b) == 1
    assert events_b[0].event_type == EventType.ERROR
    assert "JSON parse error" in events_b[0].error_message
    assert parser_b.error_count == 1

    # --- 5c: 嵌套标记 ---
    print("\n  5c: 嵌套/重复 START 标记")
    print("  场景: 两个 START 后跟一个 END（异常写入）")
    print()

    parser_c = StreamingSentinelParser()
    # 第一个 START 后又出现第二个 START，然后是 END
    # 原实现 indexOf(END, startIdx) 会匹配第一个 START 到第一个 END
    # 中间的第二个 START 会被当作 JSON 内容（解析失败）
    chunk_c = (
        f"{OUTPUT_START}\n"
        f"{OUTPUT_START}\n"
        '{"status":"success","result":"nested"}\n'
        f"{OUTPUT_END}\n"
    )
    events_c = parser_c.feed(chunk_c)
    print(f"    feed() 返回 {len(events_c)} 个事件:")
    _print_events(events_c)
    print(f"    -> 第一个 START 到第一个 END 的内容包含第二个 START，JSON 解析失败")

    assert len(events_c) == 1
    # 内容是 "---NANOCLAW_OUTPUT_START---\n{...}" 无法解析为 JSON
    assert events_c[0].event_type == EventType.ERROR

    # --- 5d: 正常输出跟在异常之后 ---
    print("\n  5d: 错误后恢复")
    print("  场景: 一个异常标记对后跟一个正常标记对")
    print()

    parser_d = StreamingSentinelParser()
    chunk_d = (
        f"{OUTPUT_START}\nbroken-json\n{OUTPUT_END}\n"
        f"{OUTPUT_START}\n"
        + json.dumps({"status": "success", "result": "恢复正常"})
        + f"\n{OUTPUT_END}\n"
    )
    events_d = parser_d.feed(chunk_d)
    print(f"    feed() 返回 {len(events_d)} 个事件:")
    _print_events(events_d)

    assert len(events_d) == 2
    assert events_d[0].event_type == EventType.ERROR
    assert events_d[1].event_type == EventType.OUTPUT
    assert events_d[1].output.result == "恢复正常"
    assert parser_d.parsed_count == 1
    assert parser_d.error_count == 1

    print(f"\n  parser_d: parsed={parser_d.parsed_count}, errors={parser_d.error_count}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("NanoClaw 流式哨兵标记解析 — 机制 Demo\n")
    demo_basic_parsing()
    demo_chunk_boundary()
    demo_multiple_outputs()
    demo_mixed_content()
    demo_malformed()
    print("=" * 64)
    print("全部 5 个场景通过")
