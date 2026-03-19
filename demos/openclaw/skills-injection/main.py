"""
OpenClaw — Skills Injection 机制复现

复现 OpenClaw 的 Skills 按需匹配注入 prompt：
- 51+ Skills 目录扫描
- 关键词匹配（每轮最多注入 1 个）
- SKILL.md 内容注入到 system prompt

对应源码: skills/*/SKILL.md, src/agents/system-prompt.ts
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── 数据模型 ──────────────────────────────────────────────────────

@dataclass
class Skill:
    """Skill 定义"""
    name: str
    triggers: list[str]     # 触发关键词
    description: str
    content: str            # SKILL.md 内容


@dataclass
class SkillMatch:
    """匹配结果"""
    skill: Skill
    matched_trigger: str
    score: float


# ── Skills 引擎 ──────────────────────────────────────────────────

class SkillsEngine:
    """
    OpenClaw Skills 注入引擎复现

    机制：
    1. 启动时扫描 skills/ 目录，加载所有 SKILL.md
    2. 每轮对话开始时，用用户消息匹配关键词
    3. 最多注入 1 个最佳匹配的 Skill
    4. Skill 内容追加到 system prompt 的 Skills section
    """

    def __init__(self):
        self.skills: list[Skill] = []

    def register(self, skill: Skill):
        self.skills.append(skill)

    def match(self, user_message: str, max_results: int = 1) -> list[SkillMatch]:
        """匹配用户消息，返回最佳 Skill"""
        msg_lower = user_message.lower()
        matches: list[SkillMatch] = []

        for skill in self.skills:
            best_trigger = ""
            best_score = 0.0

            for trigger in skill.triggers:
                trigger_lower = trigger.lower()
                if trigger_lower in msg_lower:
                    # 分数：匹配的关键词越长、越精确，分数越高
                    score = len(trigger_lower) / len(msg_lower) if msg_lower else 0
                    if score > best_score:
                        best_score = score
                        best_trigger = trigger

            if best_trigger:
                matches.append(SkillMatch(
                    skill=skill,
                    matched_trigger=best_trigger,
                    score=best_score,
                ))

        # 按分数排序，取最佳
        matches.sort(key=lambda m: -m.score)
        return matches[:max_results]

    def inject_to_prompt(self, base_prompt: str, user_message: str) -> tuple[str, str | None]:
        """将匹配的 Skill 注入到 prompt，返回 (新 prompt, 匹配的 skill 名)"""
        matches = self.match(user_message)
        if not matches:
            return base_prompt, None

        skill = matches[0].skill
        skill_section = (
            f"\n\n# Skills\n"
            f"A skill matched the current task: **{skill.name}**\n"
            f"Read the SKILL.md before proceeding:\n\n"
            f"```\n{skill.content}\n```"
        )
        return base_prompt + skill_section, skill.name


# ── 预定义 Skills ────────────────────────────────────────────────

DEMO_SKILLS = [
    Skill(
        name="github",
        triggers=["github", "pull request", "PR", "issue", "gh ", "repository"],
        description="GitHub operations via gh CLI",
        content=(
            "# GitHub Skill\n"
            "Use the `gh` CLI for all GitHub operations.\n"
            "- Create PR: `gh pr create --title \"...\" --body \"...\"`\n"
            "- Review PR: `gh pr review <number> --approve`\n"
            "- List issues: `gh issue list`"
        ),
    ),
    Skill(
        name="1password",
        triggers=["1password", "password", "secret", "credential", "vault"],
        description="1Password secret management",
        content=(
            "# 1Password Skill\n"
            "Use `op` CLI to manage secrets.\n"
            "- Get secret: `op read op://vault/item/field`\n"
            "- Never store secrets in plain text files."
        ),
    ),
    Skill(
        name="notion",
        triggers=["notion", "wiki", "knowledge base", "documentation"],
        description="Notion integration",
        content=(
            "# Notion Skill\n"
            "Use Notion API to manage pages and databases.\n"
            "- Search: POST /search with query\n"
            "- Create page: POST /pages"
        ),
    ),
    Skill(
        name="coding-agent",
        triggers=["refactor", "implement", "code review", "debug", "unit test", "fix bug"],
        description="Coding best practices",
        content=(
            "# Coding Agent Skill\n"
            "Follow these practices:\n"
            "1. Read existing code before modifying\n"
            "2. Write tests alongside implementation\n"
            "3. Keep changes minimal and focused\n"
            "4. Run linter after changes"
        ),
    ),
    Skill(
        name="image-gen",
        triggers=["generate image", "create image", "draw", "illustration", "dalle", "midjourney"],
        description="Image generation",
        content=(
            "# Image Generation Skill\n"
            "Use the `image` tool to generate images.\n"
            "- Provide detailed, descriptive prompts\n"
            "- Specify style, composition, and mood"
        ),
    ),
]


# ── Demo ──────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("OpenClaw Skills Injection Demo")
    print("=" * 64)

    engine = SkillsEngine()
    for skill in DEMO_SKILLS:
        engine.register(skill)

    # ── 1. Skills 目录 ──
    print(f"\n── 1. 已注册 Skills ({len(engine.skills)}) ──")
    for skill in engine.skills:
        print(f"  {skill.name:15s}: triggers={skill.triggers[:3]}...")

    # ── 2. 匹配测试 ──
    print("\n── 2. 关键词匹配 ──")
    test_messages = [
        "帮我创建一个 GitHub pull request",
        "请 refactor 这段代码",
        "我需要从 1password vault 获取数据库密码",
        "在 Notion 里更新文档",
        "帮我 generate image of a sunset",
        "今天天气怎么样",  # 无匹配
    ]

    for msg in test_messages:
        matches = engine.match(msg)
        if matches:
            m = matches[0]
            print(f"  \"{msg[:40]:40s}\" → {m.skill.name} (trigger='{m.matched_trigger}', score={m.score:.3f})")
        else:
            print(f"  \"{msg[:40]:40s}\" → 无匹配")

    # ── 3. Prompt 注入 ──
    print("\n── 3. Prompt 注入示例 ──")
    base_prompt = "You are a helpful assistant."
    new_prompt, skill_name = engine.inject_to_prompt(base_prompt, "帮我 review 这个 GitHub PR")
    print(f"  匹配 Skill: {skill_name}")
    print(f"  原始 Prompt: {len(base_prompt)} chars")
    print(f"  注入后 Prompt: {len(new_prompt)} chars (+{len(new_prompt) - len(base_prompt)})")
    # 打印注入的部分
    injected = new_prompt[len(base_prompt):]
    print(f"  注入内容:\n{injected}")

    # ── 4. 无匹配时不注入 ──
    print("\n── 4. 无匹配时不注入 ──")
    new_prompt, skill_name = engine.inject_to_prompt(base_prompt, "今天天气真好")
    print(f"  匹配 Skill: {skill_name}")
    print(f"  Prompt 变化: {'无' if new_prompt == base_prompt else '有'}")


if __name__ == "__main__":
    main()
