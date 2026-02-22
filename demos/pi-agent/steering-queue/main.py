"""
Pi-Agent Steering Queue Demo

演示 pi-agent 最核心创新——Steering / Follow-up 双消息队列：
  场景 1：正常执行（无中断）
  场景 2：Steering 中断（tool 执行中用户改变方向）
  场景 3：Follow-up 追加（Agent 完成后继续新任务）

原实现: packages/agent/src/agent.ts + agent-loop.ts
运行: python main.py
"""

import asyncio
from agent import Agent


async def scenario_1_normal():
    """场景 1：正常执行，无中断"""
    print("\n" + "=" * 60)
    print("场景 1：正常执行（无中断）")
    print("  用户请求实现排序函数 → Agent 读取/编辑/测试 → 完成")
    print("=" * 60 + "\n")

    agent = Agent()
    await agent.run("请帮我实现一个排序函数")


async def scenario_2_steering():
    """场景 2：Steering 中断——用户在 tool 执行中改变方向"""
    print("\n" + "=" * 60)
    print("场景 2：Steering 中断")
    print("  用户请求排序函数 → Agent 开始执行 tool")
    print("  → 用户中途发送 steering '停下，改成写文档'")
    print("  → Agent 跳过剩余 tool，响应新请求")
    print("=" * 60 + "\n")

    agent = Agent()

    async def user_interrupts():
        """模拟用户在 Agent 执行第一个 tool 后发送 steering 消息"""
        await asyncio.sleep(0.8)  # 等 Agent 执行到第一个 tool
        print("\n    👤 [用户] 发送 steering: \"停下，改成帮我写文档\"")
        agent.steer("停下，改成帮我写文档")

    # 并行：Agent 执行 + 用户中途 steering
    await asyncio.gather(
        agent.run("请帮我实现一个排序函数"),
        user_interrupts(),
    )


async def scenario_3_followup():
    """场景 3：Follow-up 追加——Agent 完成后继续新任务"""
    print("\n" + "=" * 60)
    print("场景 3：Follow-up 追加")
    print("  用户请求运行测试 → Agent 完成")
    print("  → follow-up 队列有'写文档' → Agent 继续处理")
    print("=" * 60 + "\n")

    agent = Agent()

    # 提前将 follow-up 消息入队
    agent.follow_up("帮我生成 API 文档")

    await agent.run("运行测试")


async def scenario_4_modes():
    """场景 4：对比 all vs one-at-a-time 模式"""
    print("\n" + "=" * 60)
    print("场景 4：Dequeue 模式对比")
    print("=" * 60)

    # ── one-at-a-time 模式 ──
    print("\n  ── one-at-a-time 模式（默认）──")
    print("  每次只取 1 条消息，逐个处理\n")

    agent1 = Agent()
    agent1.followup_mode = "one-at-a-time"
    agent1.follow_up("任务 A：运行测试")
    agent1.follow_up("任务 B：写文档")

    await agent1.run("任务 0：分析代码")

    # ── all 模式 ──
    print("\n  ── all 模式 ──")
    print("  一次取出所有消息，批量处理\n")

    agent2 = Agent()
    agent2.followup_mode = "all"
    agent2.follow_up("任务 A：运行测试")
    agent2.follow_up("任务 B：写文档")

    await agent2.run("任务 0：分析代码")


async def main():
    print("=" * 60)
    print("Pi-Agent Steering Queue Demo")
    print("Steering（实时中断）+ Follow-up（排队追加）双消息队列")
    print("=" * 60)

    await scenario_1_normal()
    await scenario_2_steering()
    await scenario_3_followup()
    await scenario_4_modes()

    # ── 总结 ──
    print(f"\n{'=' * 60}")
    print("核心要点:")
    print("  1. Steering: 中断 tool 执行，跳过剩余 tool，立即响应")
    print("  2. Follow-up: 等 Agent 空闲后处理，适合追加需求")
    print("  3. 双层循环: 外层=follow-up，内层=LLM+tool+steering")
    print("  4. Dequeue 模式: all=批量 / one-at-a-time=逐条")
    print("  5. 检查时机: 每个 tool 执行后都检查 steering 队列")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
