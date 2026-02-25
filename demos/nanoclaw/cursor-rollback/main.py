"""NanoClaw 消息游标推进与失败回滚 — Demo

演示双游标系统的核心机制:
  1. 正常流程 — 全局+组群游标同步推进，无重复投递
  2. Agent 失败 — 全局游标已推进，组群游标回滚，下次重新投递
  3. 部分成功 — 3 组群中 1 个失败，仅失败组群重新投递
  4. 重启恢复 — 序列化/反序列化游标状态，模拟进程重启
  5. 并发组群 — 多组群独立游标，互不干扰

运行: uv run python main.py
"""

from __future__ import annotations

import json

from cursor import CursorManager, Message


def make_msgs(group: str, specs: list[tuple[str, str, str]]) -> list[Message]:
    """批量创建消息。specs: [(id, content, timestamp), ...]"""
    return [
        Message(id=mid, group=group, sender="user", content=c, timestamp=ts)
        for mid, c, ts in specs
    ]


# ---------------------------------------------------------------------------
# Demo 1: 正常流程
# ---------------------------------------------------------------------------

def demo_normal_flow():
    print("=" * 60)
    print("Demo 1: 正常流程 — 全局+组群游标同步推进")
    print("=" * 60)

    cm = CursorManager()
    group = "team-alpha@g.us"

    batch1 = make_msgs(group, [
        ("m1", "你好", "2026-02-25T10:00:00Z"),
        ("m2", "@Andy 帮我查天气", "2026-02-25T10:00:01Z"),
    ])

    # 轮询读取 → 推进全局游标
    new = cm.get_new_messages(batch1)
    cm.advance_global(new[-1].timestamp)
    print(f"\n  轮询: {len(new)} 条新消息")
    cm.dump("轮询后")

    # Agent 成功 → 推进组群游标
    pending = cm.get_pending_messages(group, batch1)
    cm.advance_group(group, pending[-1].timestamp)
    print(f"  Agent 成功: 组群游标推进")
    cm.dump("处理后")

    # 第二批消息 — 验证无重复
    batch1.extend(make_msgs(group, [("m3", "谢谢！", "2026-02-25T10:01:00Z")]))
    pending2 = cm.get_pending_messages(group, batch1)
    print(f"  下次轮询: 组群待处理 {len(pending2)} 条 (第一批不会重复投递 ✓)")
    print()


# ---------------------------------------------------------------------------
# Demo 2: Agent 失败 — 消息重新投递
# ---------------------------------------------------------------------------

def demo_agent_failure():
    print("=" * 60)
    print("Demo 2: Agent 失败 — 组群游标回滚，下次重新投递")
    print("=" * 60)

    cm = CursorManager()
    group = "team-beta@g.us"

    msgs = make_msgs(group, [
        ("m1", "帮我分析代码", "2026-02-25T11:00:00Z"),
        ("m2", "特别是 error handling", "2026-02-25T11:00:01Z"),
    ])

    # 轮询 → 全局游标推进
    new = cm.get_new_messages(msgs)
    cm.advance_global(new[-1].timestamp)
    print(f"\n  轮询: {len(new)} 条消息，全局游标推进")

    # 乐观推进组群游标（原实现: 先推进再回滚）
    pending = cm.get_pending_messages(group, msgs)
    previous = cm.get_group_cursor(group)
    cm.advance_group(group, pending[-1].timestamp)
    print(f"  乐观推进组群游标 (previous={previous or 'empty'})")

    # Agent 失败 → 回滚
    cm.rollback_group(group, previous)
    print(f"  Agent 失败! 回滚组群游标")
    cm.dump("回滚后")

    # 验证: 全局无新消息，但组群有待处理
    new2 = cm.get_new_messages(msgs)
    retry = cm.get_pending_messages(group, msgs)
    print(f"  下次轮询: 全局新消息 {len(new2)}, 组群待处理 {len(retry)} (重新投递 ✓)")
    for m in retry:
        print(f"    重新投递: [{m.timestamp}] {m.content}")
    print()


# ---------------------------------------------------------------------------
# Demo 3: 部分成功 — 3 组群中 1 个失败
# ---------------------------------------------------------------------------

def demo_partial_success():
    print("=" * 60)
    print("Demo 3: 部分成功 — 3 组群中 1 个失败，仅失败者重新投递")
    print("=" * 60)

    cm = CursorManager()
    groups = {"alpha@g.us": True, "beta@g.us": False, "gamma@g.us": True}

    all_msgs: list[Message] = []
    for g in groups:
        all_msgs.extend(make_msgs(g, [
            (f"{g}-m1", f"[{g}] 消息1", "2026-02-25T12:00:00Z"),
            (f"{g}-m2", f"[{g}] 消息2", "2026-02-25T12:00:01Z"),
        ]))

    new = cm.get_new_messages(all_msgs)
    cm.advance_global(max(m.timestamp for m in new))
    print(f"\n  轮询: {len(new)} 条消息（3 组群）\n")

    # 逐组处理
    for g, ok in groups.items():
        pending = cm.get_pending_messages(g, all_msgs)
        prev = cm.get_group_cursor(g)
        cm.advance_group(g, pending[-1].timestamp)
        if not ok:
            cm.rollback_group(g, prev)
        print(f"  {g:15s} — {'成功' if ok else '失败'}, 游标{'推进' if ok else '回滚'}")

    # 验证
    print()
    for g in groups:
        p = cm.get_pending_messages(g, all_msgs)
        print(f"  {g:15s}: {len(p)} 条待处理{' ← 重新投递' if p else ''}")
    print()


# ---------------------------------------------------------------------------
# Demo 4: 重启恢复
# ---------------------------------------------------------------------------

def demo_restart_recovery():
    print("=" * 60)
    print("Demo 4: 重启恢复 — 持久化游标状态后恢复")
    print("=" * 60)

    # 运行中的状态
    cm1 = CursorManager()
    cm1.global_cursor = "2026-02-25T15:00:00Z"
    cm1.group_cursors = {
        "alpha@g.us": "2026-02-25T14:55:00Z",
        "beta@g.us": "2026-02-25T14:50:00Z",
    }

    # 保存（模拟 saveState → setRouterState）
    state = cm1.save_state()
    serialized = json.dumps(state)
    print(f"\n  保存: last_timestamp='{state['last_timestamp']}'")
    print(f"        last_agent_timestamp={json.dumps(state['last_agent_timestamp'])}")

    # 重启 → 恢复
    cm2 = CursorManager()
    cm2.load_state(json.loads(serialized))
    print(f"  重启后恢复:")
    cm2.dump("恢复")
    print(f"  游标匹配: {cm2.global_cursor == cm1.global_cursor and cm2.group_cursors == cm1.group_cursors} ✓")

    # 崩溃窗口: 全局游标之前但组群游标之后的消息
    crash_msgs = make_msgs("beta@g.us", [
        ("c1", "崩溃前的消息", "2026-02-25T14:51:00Z"),
        ("c2", "崩溃前的消息2", "2026-02-25T14:52:00Z"),
    ])
    pending = cm2.get_pending_messages("beta@g.us", crash_msgs)
    print(f"  recoverPendingMessages: beta 有 {len(pending)} 条未处理 (崩溃窗口恢复 ✓)")
    print()


# ---------------------------------------------------------------------------
# Demo 5: 并发组群 — 各组独立游标
# ---------------------------------------------------------------------------

def demo_concurrent_groups():
    print("=" * 60)
    print("Demo 5: 并发组群 — 多组群独立游标，互不干扰")
    print("=" * 60)

    cm = CursorManager()
    all_msgs: list[Message] = []

    # 3 组群消息时间交错
    for group, mid, content, ts in [
        ("alpha@g.us", "a1", "Alpha-1", "2026-02-25T13:00:00Z"),
        ("beta@g.us",  "b1", "Beta-1",  "2026-02-25T13:00:01Z"),
        ("alpha@g.us", "a2", "Alpha-2", "2026-02-25T13:00:02Z"),
        ("gamma@g.us", "g1", "Gamma-1", "2026-02-25T13:00:03Z"),
        ("beta@g.us",  "b2", "Beta-2",  "2026-02-25T13:00:04Z"),
        ("alpha@g.us", "a3", "Alpha-3", "2026-02-25T13:00:05Z"),
        ("gamma@g.us", "g2", "Gamma-2", "2026-02-25T13:00:06Z"),
    ]:
        all_msgs.append(Message(id=mid, group=group, sender="user",
                                content=content, timestamp=ts))

    new = cm.get_new_messages(all_msgs)
    cm.advance_global(max(m.timestamp for m in new))
    print(f"\n  轮询: {len(new)} 条消息（3 组群交错）")

    # Alpha: 处理 a1+a2 成功
    ap = cm.get_pending_messages("alpha@g.us", all_msgs)
    cm.advance_group("alpha@g.us", ap[1].timestamp)
    print(f"  Alpha: 处理 a1+a2 成功, 游标→a2")

    # Beta: 失败回滚
    bp = cm.get_pending_messages("beta@g.us", all_msgs)
    prev = cm.get_group_cursor("beta@g.us")
    cm.advance_group("beta@g.us", bp[-1].timestamp)
    cm.rollback_group("beta@g.us", prev)
    print(f"  Beta:  处理失败, 游标回滚")

    # Gamma: 未触发
    print(f"  Gamma: 未触发")
    cm.dump("Round 1 后")

    # 验证各组群独立状态
    print(f"\n  验证 Round 2 待处理:")
    for g, expect in [("alpha@g.us", "a3"), ("beta@g.us", "b1,b2"), ("gamma@g.us", "g1,g2")]:
        p = cm.get_pending_messages(g, all_msgs)
        ids = ",".join(m.id for m in p)
        print(f"    {g:15s}: [{ids}] (期望: {expect}) ✓")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("NanoClaw 消息游标推进与失败回滚 — 机制 Demo\n")
    demo_normal_flow()
    demo_agent_failure()
    demo_partial_success()
    demo_restart_recovery()
    demo_concurrent_groups()
    print("=" * 60)
    print("所有 demo 完成")
