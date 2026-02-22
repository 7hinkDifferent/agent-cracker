"""
Codex CLI — 多层 Prompt 组装 Demo

演示 codex-cli 的 7 层 prompt 模板叠加组装机制：
- 基础指令 → 人格注入 → 策略约束 → 协作模式 → 记忆工具 → 自定义指令 → slash 命令
- 不同配置组合下的 prompt 差异对比

Run: uv run python main.py
"""

from assembler import AssemblyConfig, assemble, render


def print_section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


print("=" * 60)
print("  Codex CLI — 多层 Prompt 组装 Demo")
print("  复现 build_initial_context() 的 7 层模板叠加")
print("=" * 60)


# ── Demo 1: 逐层展示 ─────────────────────────────────────────────

print_section("Demo 1: 逐层展示（默认配置）")

config = AssemblyConfig(
    personality="pragmatic",
    collaboration_mode="default",
    sandbox_policy="workspace-write",
    approval_policy="auto-edit",
    custom_instructions="Always use TypeScript for new files.",
    slash_command="review",
)
layers = assemble(config)

for i, layer in enumerate(layers, 1):
    print(f"\n  Layer {i}: {layer.name}")
    print(f"  来源: {layer.source}")
    print(f"  {'·' * 40}")
    for line in layer.content.split("\n")[:5]:
        print(f"    {line}")
    if len(layer.content.split("\n")) > 5:
        print(f"    ... ({len(layer.content.split(chr(10)))} 行)")

print(f"\n  共 {len(layers)} 层")


# ── Demo 2: 人格切换对比 ─────────────────────────────────────────

print_section("Demo 2: 人格切换对比（pragmatic vs friendly）")

for personality in ["pragmatic", "friendly"]:
    config = AssemblyConfig(personality=personality)
    layers = assemble(config)
    prompt = render(layers)
    print(f"\n  [{personality}] prompt 长度: {len(prompt)} chars")
    # 显示人格层内容
    for layer in layers:
        if layer.name == "Personality":
            for line in layer.content.split("\n"):
                print(f"    {line}")


# ── Demo 3: 协作模式切换 ─────────────────────────────────────────

print_section("Demo 3: 协作模式切换（default vs plan）")

for mode in ["default", "plan"]:
    config = AssemblyConfig(collaboration_mode=mode)
    layers = assemble(config)
    print(f"\n  [{mode}] 模式:")
    for layer in layers:
        if layer.name == "Collaboration Mode":
            for line in layer.content.split("\n"):
                print(f"    {line}")


# ── Demo 4: 策略约束变化 ─────────────────────────────────────────

print_section("Demo 4: 不同沙箱策略下的约束注入")

for sandbox in ["read-only", "workspace-write", "full-access"]:
    config = AssemblyConfig(sandbox_policy=sandbox)
    layers = assemble(config)
    for layer in layers:
        if layer.name == "Policy Constraints":
            print(f"\n  [{sandbox}]:")
            for line in layer.content.split("\n"):
                print(f"    {line}")


# ── Demo 5: 最终 Prompt 渲染 ─────────────────────────────────────

print_section("Demo 5: 完整配置 → 最终 System Prompt")

config = AssemblyConfig(
    personality="friendly",
    collaboration_mode="plan",
    sandbox_policy="read-only",
    approval_policy="suggest",
    enable_memory=True,
    custom_instructions="This is a Django project. Use Python 3.12.",
    slash_command="explain",
)

layers = assemble(config)
prompt = render(layers)

print(f"\n  配置:")
print(f"    人格: {config.personality}")
print(f"    模式: {config.collaboration_mode}")
print(f"    沙箱: {config.sandbox_policy}")
print(f"    审批: {config.approval_policy}")
print(f"    记忆: {'启用' if config.enable_memory else '禁用'}")
print(f"    自定义: {config.custom_instructions}")
print(f"    Slash: /{config.slash_command}")
print(f"\n  最终 prompt ({len(layers)} 层, {len(prompt)} chars):")
print(f"  {'·' * 50}")

# 显示前 30 行
lines = prompt.split("\n")
for line in lines[:30]:
    print(f"    {line}")
if len(lines) > 30:
    print(f"    ... 共 {len(lines)} 行")

print(f"\n{'=' * 60}")
print("  Demo 完成")
print(f"{'=' * 60}")
