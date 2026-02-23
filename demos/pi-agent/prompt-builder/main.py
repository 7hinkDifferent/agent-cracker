"""
Pi-Agent Prompt Builder Demo

复现 Pi-Agent 的分层 System Prompt 组装机制：
- 角色定义（固定基础）
- 工具描述（动态注入 tool schema）
- 自适应指南（根据工具组合生成条件建议）
- 项目上下文注入（.pi/context/*.md）
- 元信息（时间戳、工作目录）

Run: python main.py
"""

from builder import (
    PromptBuilder, ToolDef, ToolParam,
    ALL_TOOLS, BASIC_TOOLS,
    generate_adaptive_guidelines,
)


def demo_guidelines():
    """演示不同工具组合下的自适应指南差异。"""
    print("=" * 60)
    print("Demo 1: Adaptive Guidelines (工具组合影响提示内容)")
    print("=" * 60)

    configs = [
        ("仅 bash", [ToolDef("bash", "Execute shell commands")]),
        ("bash + grep + find", [
            ToolDef("bash", "Execute shell commands"),
            ToolDef("grep", "Search patterns"),
            ToolDef("find", "Find files"),
        ]),
        ("read + edit", [
            ToolDef("read", "Read files"),
            ToolDef("edit", "Edit files"),
        ]),
        ("完整工具集", ALL_TOOLS),
    ]

    for label, tools in configs:
        guidelines = generate_adaptive_guidelines(tools)
        print(f"\n▸ {label} ({len(tools)} tools)")
        if guidelines:
            for i, g in enumerate(guidelines, 1):
                print(f"  {i}. {g}")
        else:
            print("  (no guidelines)")


def demo_full_prompt():
    """演示完整 prompt 组装过程。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Full Prompt Assembly (完整 prompt 组装)")
    print("=" * 60)

    builder = PromptBuilder(
        tools=ALL_TOOLS,
        cwd="/Users/demo/my-project",
        project_context=(
            "This is a Python web application using FastAPI.\n"
            "The main entry point is `app/main.py`.\n"
            "Tests are in the `tests/` directory."
        ),
        custom_context="Focus on writing clean, well-tested code.",
    )

    prompt = builder.build()
    messages = builder.build_messages()
    schemas = builder.get_tool_schemas()

    # 显示分段结构
    print(f"\n── System Prompt ({len(prompt)} chars) ──\n")

    # 按段落显示（截断每段）
    sections = prompt.split("\n## ")
    for i, section in enumerate(sections):
        if i == 0:
            title = "(Role Definition)"
            content = section
        else:
            title = section.split("\n")[0]
            content = "\n".join(section.split("\n")[1:])

        content_preview = content[:150].strip()
        if len(content) > 150:
            content_preview += "..."
        print(f"  [{i + 1}] {title}")
        for line in content_preview.splitlines():
            print(f"      {line}")
        print()

    # 消息格式
    print(f"── Messages Format ──\n")
    print(f"  Messages count: {len(messages)}")
    print(f"  First message role: {messages[0]['role']}")
    print(f"  Content length: {len(messages[0]['content'])} chars")

    # Tool schemas
    print(f"\n── Tool Schemas ({len(schemas)} tools) ──\n")
    for schema in schemas:
        fn = schema["function"]
        params = fn["parameters"]["properties"]
        required = fn["parameters"].get("required", [])
        print(f"  {fn['name']}: {len(params)} params ({len(required)} required)")


def demo_minimal_vs_full():
    """对比最小工具集和完整工具集的 prompt 差异。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Minimal vs Full (工具集对 prompt 的影响)")
    print("=" * 60)

    minimal = PromptBuilder(tools=BASIC_TOOLS, cwd=".")
    full = PromptBuilder(tools=ALL_TOOLS, cwd=".")

    minimal_prompt = minimal.build()
    full_prompt = full.build()

    print(f"\n  Minimal (read + edit + bash):")
    print(f"    Prompt length: {len(minimal_prompt)} chars")
    print(f"    Guidelines: {len(generate_adaptive_guidelines(BASIC_TOOLS))}")
    print(f"    Tool schemas: {len(minimal.get_tool_schemas())}")

    print(f"\n  Full (6 tools):")
    print(f"    Prompt length: {len(full_prompt)} chars")
    print(f"    Guidelines: {len(generate_adaptive_guidelines(ALL_TOOLS))}")
    print(f"    Tool schemas: {len(full.get_tool_schemas())}")

    print(f"\n  Difference: +{len(full_prompt) - len(minimal_prompt)} chars")


def main():
    print("Pi-Agent Prompt Builder Demo")
    print("Reproduces the multi-section system prompt assembly mechanism\n")

    demo_guidelines()
    demo_full_prompt()
    demo_minimal_vs_full()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("\n  5-section prompt assembly:")
    print("    1. Role definition (static base)")
    print("    2. Tool descriptions (dynamic, per active tool)")
    print("    3. Adaptive guidelines (conditional, based on tool combinations)")
    print("    4. Project context (.pi/context/ injection)")
    print("    5. Metadata (timestamp, working directory)")
    print("\n  Key insight: Guidelines adapt to available tools —")
    print("  the same agent generates different prompts for different tool sets.")
    print("\n✓ Demo complete!")


if __name__ == "__main__":
    main()
