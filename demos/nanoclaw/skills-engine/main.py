"""NanoClaw Skills Engine — Demo

演示 skills-engine 的核心机制：
  1. Install — 安装 skill（新增文件 + 三向合并修改文件）
  2. List — 列出已安装 skill 及元数据
  3. Conflict detection — 两个 skill 修改同一文件时检测冲突
  4. Uninstall — 卸载 skill，验证变更已撤回
  5. Rebase — 模拟 upstream 更新，rebase skill 到新 base

运行: uv run python main.py
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from engine import (
    ApplyResult,
    SkillManifest,
    SkillsEngine,
    create_skill_package,
    init_project,
    read_state,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def print_file(project_root: str, rel_path: str, label: str = "") -> None:
    """打印项目文件内容。"""
    fp = os.path.join(project_root, rel_path)
    if not os.path.exists(fp):
        print(f"    [{label or rel_path}] (不存在)")
        return
    content = Path(fp).read_text().rstrip()
    tag = f" ({label})" if label else ""
    print(f"    [{rel_path}]{tag}:")
    for line in content.split("\n"):
        print(f"      {line}")


def print_result(result: ApplyResult) -> None:
    """打印安装结果。"""
    status = "SUCCESS" if result.success else "FAILED"
    print(f"    结果: {status} — skill={result.skill} v{result.version}")
    if result.error:
        print(f"    错误: {result.error}")
    if result.merge_conflicts:
        print(f"    冲突文件: {', '.join(result.merge_conflicts)}")


# ---------------------------------------------------------------------------
# Demo 1: 安装 skill
# ---------------------------------------------------------------------------

def demo_install(work_dir: str) -> str:
    """安装一个 skill，演示新增文件 + 修改现有文件。"""
    print("=" * 60)
    print("Demo 1: Install Skill — 安装 skill（新增 + 修改文件）")
    print("=" * 60)

    project = os.path.join(work_dir, "project-install")

    # 初始化项目: 一个 config 和一个 index 文件
    init_project(project, files={
        "src/config.ts": 'export const CHANNELS = ["whatsapp"];\nexport const VERSION = "1.0.0";\n',
        "src/index.ts": 'import { CHANNELS } from "./config";\nconsole.log("Active:", CHANNELS);\n',
    })

    print("\n  项目初始状态:")
    print_file(project, "src/config.ts")
    print_file(project, "src/index.ts")

    # 创建 add-telegram skill
    # 这个 skill 添加 telegram.ts 并修改 config.ts
    skill_dir = os.path.join(work_dir, "skills", "add-telegram")
    create_skill_package(
        skill_dir,
        manifest=SkillManifest(
            skill="add-telegram",
            version="1.0.0",
            description="Add Telegram channel support",
            adds=["src/channels/telegram.ts"],
            modifies=["src/config.ts"],
        ),
        add_files={
            "src/channels/telegram.ts": (
                'import { Telegraf } from "telegraf";\n'
                "\n"
                "export class TelegramChannel {\n"
                "  private bot: Telegraf;\n"
                "\n"
                "  constructor(token: string) {\n"
                '    this.bot = new Telegraf(token);\n'
                "  }\n"
                "\n"
                "  async start() {\n"
                "    this.bot.launch();\n"
                "  }\n"
                "}\n"
            ),
        },
        modify_files={
            # modify/ 文件是 skill 期望的最终状态（用于三向合并）
            "src/config.ts": 'export const CHANNELS = ["whatsapp", "telegram"];\nexport const VERSION = "1.0.0";\n',
        },
    )

    engine = SkillsEngine(project)
    result = engine.install_skill(skill_dir)
    print_result(result)

    print("\n  安装后文件状态:")
    print_file(project, "src/config.ts", "被修改")
    print_file(project, "src/channels/telegram.ts", "新增")

    # 验证状态
    state = read_state(project)
    print(f"\n  已安装 skills: {[s.name for s in state.applied_skills]}")
    print(f"  文件哈希数: {sum(len(s.file_hashes) for s in state.applied_skills)}")
    print()

    return project


# ---------------------------------------------------------------------------
# Demo 2: 列出已安装 skills
# ---------------------------------------------------------------------------

def demo_list(project: str) -> None:
    """列出已安装 skills 及其元数据。"""
    print("=" * 60)
    print("Demo 2: List Skills — 列出已安装 skill 及元数据")
    print("=" * 60)

    engine = SkillsEngine(project)
    skills = engine.list_skills()

    print(f"\n  已安装 {len(skills)} 个 skill:\n")
    for skill in skills:
        print(f"    - {skill.name} v{skill.version}")
        print(f"      安装时间: {skill.applied_at}")
        print(f"      跟踪文件: {list(skill.file_hashes.keys())}")
        for path, hash_val in skill.file_hashes.items():
            print(f"        {path}: {hash_val[:16]}...")
    print()


# ---------------------------------------------------------------------------
# Demo 3: 冲突检测
# ---------------------------------------------------------------------------

def demo_conflict_detection(work_dir: str) -> None:
    """两个 skill 修改同一文件 -> 检测冲突。"""
    print("=" * 60)
    print("Demo 3: Conflict Detection — 声明式 + 文件级冲突检测")
    print("=" * 60)

    project = os.path.join(work_dir, "project-conflict")

    init_project(project, files={
        "src/config.ts": 'export const CHANNELS = ["whatsapp"];\n',
    })

    # 安装 skill-a (修改 config.ts)
    skill_a_dir = os.path.join(work_dir, "skills", "skill-a")
    create_skill_package(
        skill_a_dir,
        manifest=SkillManifest(
            skill="skill-a",
            version="1.0.0",
            description="Skill A — modifies config",
            modifies=["src/config.ts"],
            conflicts=["skill-b"],  # 声明与 skill-b 互斥
        ),
        modify_files={
            "src/config.ts": 'export const CHANNELS = ["whatsapp", "a-feature"];\n',
        },
    )

    engine = SkillsEngine(project)
    result = engine.install_skill(skill_a_dir)
    print(f"\n  安装 skill-a: {'SUCCESS' if result.success else 'FAILED'}")

    # 创建 skill-b (也修改 config.ts, 且被 skill-a 声明为 conflicts)
    skill_b_dir = os.path.join(work_dir, "skills", "skill-b")
    create_skill_package(
        skill_b_dir,
        manifest=SkillManifest(
            skill="skill-b",
            version="1.0.0",
            description="Skill B — conflicts with A",
            modifies=["src/config.ts"],
            conflicts=["skill-a"],
        ),
        modify_files={
            "src/config.ts": 'export const CHANNELS = ["whatsapp", "b-feature"];\n',
        },
    )

    # 检测冲突（安装前检测）
    print("\n  尝试安装 skill-b 前的冲突检测:")
    conflicts = engine.detect_conflicts(skill_b_dir)
    for c in conflicts:
        print(f"    - {c}")

    # 尝试安装（应被声明式冲突阻止）
    result_b = engine.install_skill(skill_b_dir)
    print(f"\n  安装 skill-b: {'SUCCESS' if result_b.success else 'FAILED'}")
    if result_b.error:
        print(f"    原因: {result_b.error}")

    # 创建 skill-c (修改同一文件但无声明冲突)
    skill_c_dir = os.path.join(work_dir, "skills", "skill-c")
    create_skill_package(
        skill_c_dir,
        manifest=SkillManifest(
            skill="skill-c",
            version="1.0.0",
            description="Skill C — overlapping files, no declared conflict",
            modifies=["src/config.ts"],
        ),
        modify_files={
            "src/config.ts": 'export const CHANNELS = ["whatsapp", "c-feature"];\n',
        },
    )

    print("\n  skill-c 的冲突检测（无声明冲突，但有文件重叠）:")
    conflicts_c = engine.detect_conflicts(skill_c_dir)
    for c in conflicts_c:
        print(f"    - {c}")
    print()


# ---------------------------------------------------------------------------
# Demo 4: 卸载 skill
# ---------------------------------------------------------------------------

def demo_uninstall(work_dir: str) -> None:
    """卸载 skill，验证变更被撤回。"""
    print("=" * 60)
    print("Demo 4: Uninstall — 卸载 skill 并验证变更撤回")
    print("=" * 60)

    project = os.path.join(work_dir, "project-uninstall")

    init_project(project, files={
        "src/config.ts": 'export const CHANNELS = ["whatsapp"];\nexport const PORT = 3000;\n',
    })

    # 安装 skill
    skill_dir = os.path.join(work_dir, "skills", "add-discord")
    create_skill_package(
        skill_dir,
        manifest=SkillManifest(
            skill="add-discord",
            version="1.0.0",
            description="Add Discord channel",
            adds=["src/channels/discord.ts"],
            modifies=["src/config.ts"],
        ),
        add_files={
            "src/channels/discord.ts": (
                'import { Client } from "discord.js";\n'
                "export class DiscordChannel {}\n"
            ),
        },
        modify_files={
            "src/config.ts": 'export const CHANNELS = ["whatsapp", "discord"];\nexport const PORT = 3000;\n',
        },
    )

    engine = SkillsEngine(project)
    install_result = engine.install_skill(skill_dir)
    print(f"\n  安装 add-discord: {'SUCCESS' if install_result.success else 'FAILED'}")

    print("\n  安装后:")
    print_file(project, "src/config.ts")
    discord_exists = os.path.exists(os.path.join(project, "src/channels/discord.ts"))
    print(f"    discord.ts 存在: {discord_exists}")

    # 卸载
    uninstall_result = engine.uninstall_skill("add-discord")
    print(f"\n  卸载 add-discord: {'SUCCESS' if uninstall_result.success else 'FAILED'}")
    if uninstall_result.error:
        print(f"    错误: {uninstall_result.error}")

    print("\n  卸载后:")
    print_file(project, "src/config.ts")
    discord_exists = os.path.exists(os.path.join(project, "src/channels/discord.ts"))
    print(f"    discord.ts 存在: {discord_exists}")

    state = read_state(project)
    print(f"\n  已安装 skills: {[s.name for s in state.applied_skills]}")
    print()


# ---------------------------------------------------------------------------
# Demo 5: Rebase — upstream 更新后 rebase
# ---------------------------------------------------------------------------

def demo_rebase(work_dir: str) -> None:
    """模拟 upstream 更新，rebase skill 变更到新 base。"""
    print("=" * 60)
    print("Demo 5: Rebase — Upstream 更新后 rebase skill 变更")
    print("=" * 60)

    project = os.path.join(work_dir, "project-rebase")

    init_project(project, files={
        "src/config.ts": 'export const VERSION = "1.0.0";\nexport const CHANNELS = ["whatsapp"];\n',
        "src/index.ts": '// NanoClaw v1.0\nconsole.log("hello");\n',
    })

    # 安装一个 skill
    skill_dir = os.path.join(work_dir, "skills", "add-voice")
    create_skill_package(
        skill_dir,
        manifest=SkillManifest(
            skill="add-voice",
            version="1.0.0",
            description="Add voice transcription",
            adds=["src/voice.ts"],
            modifies=["src/config.ts"],
        ),
        add_files={
            "src/voice.ts": "// Whisper voice transcription\nexport class VoiceTranscriber {}\n",
        },
        modify_files={
            "src/config.ts": 'export const VERSION = "1.0.0";\nexport const CHANNELS = ["whatsapp"];\nexport const VOICE_ENABLED = true;\n',
        },
    )

    engine = SkillsEngine(project)
    result = engine.install_skill(skill_dir)
    print(f"\n  安装 add-voice: {'SUCCESS' if result.success else 'FAILED'}")

    print("\n  当前工作树（安装 skill 后）:")
    print_file(project, "src/config.ts")
    print_file(project, "src/voice.ts")

    # 模拟 upstream 更新: VERSION 升到 2.0, index.ts 改变
    # 不使用三向合并 rebase（需要旧 base backup），用 flatten 模式演示
    print("\n  执行 Flatten Rebase（将 skill 变更烘焙进 base）...")
    rebase_result = engine.rebase()

    print(f"    结果: {'SUCCESS' if rebase_result.success else 'FAILED'}")
    print(f"    归档 patch 文件数: {rebase_result.files_in_patch}")
    if rebase_result.patch_file:
        patch_content = Path(rebase_result.patch_file).read_text()
        patch_lines = patch_content.count("\n")
        print(f"    patch 文件: {rebase_result.patch_file} ({patch_lines} 行)")
    if rebase_result.rebased_at:
        print(f"    rebased_at: {rebase_result.rebased_at}")

    # 验证 rebase 后状态
    state = read_state(project)
    print(f"\n  rebase 后已安装 skills: {[s.name for s in state.applied_skills]}")
    print(f"  rebased_at: {state.rebased_at}")

    # 验证 rebase 后不能单独卸载
    print("\n  尝试在 rebase 后卸载 skill:")
    uninstall_result = engine.uninstall_skill("add-voice")
    print(f"    结果: {'SUCCESS' if uninstall_result.success else 'FAILED'}")
    if uninstall_result.error:
        print(f"    原因: {uninstall_result.error}")

    # 验证 base 目录已更新
    base_config = os.path.join(project, ".nanoclaw/base/src/config.ts")
    if os.path.exists(base_config):
        content = Path(base_config).read_text()
        has_voice = "VOICE_ENABLED" in content
        print(f"\n  base/src/config.ts 包含 VOICE_ENABLED: {has_voice}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("NanoClaw Skills Engine -- 机制 Demo\n")

    # 使用临时目录隔离所有 git/文件操作
    with tempfile.TemporaryDirectory(prefix="nanoclaw-skills-") as work_dir:
        # 初始化一个 git repo（merge_file 需要 git）
        os.system(f"git init -q {work_dir}")
        os.environ["GIT_WORK_TREE"] = work_dir
        os.environ["GIT_DIR"] = os.path.join(work_dir, ".git")

        # Demo 1: 安装
        project = demo_install(work_dir)

        # Demo 2: 列出 (复用 demo1 的项目)
        demo_list(project)

        # Demo 3: 冲突检测
        demo_conflict_detection(work_dir)

        # Demo 4: 卸载
        demo_uninstall(work_dir)

        # Demo 5: Rebase
        demo_rebase(work_dir)

    print("All 5 demos completed.")
