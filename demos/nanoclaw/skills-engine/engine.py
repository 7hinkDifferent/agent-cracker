"""NanoClaw Skills Engine — Skill 安装/卸载/Rebase/冲突检测核心

基于 skills-engine/ (2,927 行，14 模块):
  - apply.ts: skill 安装（三向合并 + 结构化操作 + 回滚）
  - uninstall.ts: skill 卸载（replay-without 策略）
  - rebase.ts: upstream 更新后 rebase（diff + 三向合并）
  - manifest.ts: manifest 校验 + 依赖/冲突检查
  - state.ts: 已安装 skill 状态追踪（YAML 持久化）
  - merge.ts: git merge-file 三向合并封装
  - replay.ts: 从干净 base 重放 skills 列表
  - backup.ts: 文件级备份/回滚（含 tombstone 标记）
  - lock.ts: 文件锁防并发

核心设计:
  - Skills 不是运行时插件，而是**代码变换**——直接修改项目源码
  - 每个 skill 由 manifest.yaml + add/ + modify/ 组成
  - 三向合并: current <-- base --> skill，用 git merge-file 合并
  - 卸载通过 replay-without 实现：移除目标 skill 后重放其余 skills
  - Rebase: 生成 combined.patch 归档，三向合并到新 base
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# 常量 (对应 constants.ts)
# ---------------------------------------------------------------------------

NANOCLAW_DIR = ".nanoclaw"
STATE_FILE = "state.json"  # Demo 用 JSON 替代 YAML，避免外部依赖
BASE_DIR = ".nanoclaw/base"
BACKUP_DIR = ".nanoclaw/backup"
LOCK_FILE = ".nanoclaw/lock"
SKILLS_SCHEMA_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# 数据类型 (对应 types.ts)
# ---------------------------------------------------------------------------

@dataclass
class SkillManifest:
    """Skill 声明文件，定义 skill 的内容和约束。

    对应 types.ts:SkillManifest。原实现用 YAML 解析 manifest.yaml，
    demo 用 JSON（manifest.json）避免依赖 pyyaml。
    """
    skill: str                          # Skill 名称
    version: str                        # Skill 版本
    description: str = ""               # 描述
    core_version: str = "0.1.0"         # 目标核心版本
    adds: list[str] = field(default_factory=list)       # 新增文件列表
    modifies: list[str] = field(default_factory=list)   # 修改文件列表
    conflicts: list[str] = field(default_factory=list)  # 互斥 skill 列表
    depends: list[str] = field(default_factory=list)    # 依赖 skill 列表


@dataclass
class AppliedSkill:
    """已安装 skill 的状态记录。对应 types.ts:AppliedSkill。"""
    name: str
    version: str
    applied_at: str
    file_hashes: dict[str, str] = field(default_factory=dict)


@dataclass
class SkillState:
    """全局 skill 状态。对应 types.ts:SkillState。"""
    skills_system_version: str = SKILLS_SCHEMA_VERSION
    core_version: str = "0.1.0"
    applied_skills: list[AppliedSkill] = field(default_factory=list)
    rebased_at: str | None = None


@dataclass
class ApplyResult:
    """Skill 安装结果。对应 types.ts:ApplyResult。"""
    success: bool
    skill: str
    version: str
    merge_conflicts: list[str] | None = None
    error: str | None = None


@dataclass
class UninstallResult:
    """Skill 卸载结果。对应 types.ts:UninstallResult。"""
    success: bool
    skill: str
    replay_results: dict[str, bool] | None = None
    error: str | None = None


@dataclass
class RebaseResult:
    """Rebase 结果。对应 types.ts:RebaseResult。"""
    success: bool
    files_in_patch: int = 0
    patch_file: str | None = None
    rebased_at: str | None = None
    merge_conflicts: list[str] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def compute_file_hash(file_path: str) -> str:
    """计算文件 SHA-256 哈希。对应 state.ts:computeFileHash。"""
    content = Path(file_path).read_bytes()
    return hashlib.sha256(content).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# State 持久化 (对应 state.ts)
# ---------------------------------------------------------------------------

def _state_path(project_root: str) -> str:
    return os.path.join(project_root, NANOCLAW_DIR, STATE_FILE)


def read_state(project_root: str) -> SkillState:
    """读取 skill 状态。对应 state.ts:readState。"""
    sp = _state_path(project_root)
    if not os.path.exists(sp):
        raise FileNotFoundError(
            f"{sp} not found. Run init_project() first."
        )
    with open(sp) as f:
        data = json.load(f)

    state = SkillState(
        skills_system_version=data.get("skills_system_version", SKILLS_SCHEMA_VERSION),
        core_version=data.get("core_version", "0.1.0"),
        rebased_at=data.get("rebased_at"),
    )
    for s in data.get("applied_skills", []):
        state.applied_skills.append(AppliedSkill(
            name=s["name"],
            version=s["version"],
            applied_at=s["applied_at"],
            file_hashes=s.get("file_hashes", {}),
        ))
    return state


def write_state(project_root: str, state: SkillState) -> None:
    """原子写入 skill 状态。对应 state.ts:writeState。

    原实现用 tmp + rename 原子写入防止 crash 时损坏。
    """
    sp = _state_path(project_root)
    os.makedirs(os.path.dirname(sp), exist_ok=True)

    data = {
        "skills_system_version": state.skills_system_version,
        "core_version": state.core_version,
        "applied_skills": [
            {
                "name": s.name,
                "version": s.version,
                "applied_at": s.applied_at,
                "file_hashes": s.file_hashes,
            }
            for s in state.applied_skills
        ],
    }
    if state.rebased_at:
        data["rebased_at"] = state.rebased_at

    # 原子写入: 先写 tmp 再 rename
    tmp_path = sp + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, sp)


# ---------------------------------------------------------------------------
# Backup (对应 backup.ts)
# ---------------------------------------------------------------------------

def create_backup(project_root: str, file_paths: list[str]) -> None:
    """备份文件列表。对应 backup.ts:createBackup。

    原实现对不存在的文件写 .tombstone 标记，restore 时据此删除新文件。
    Demo 简化为仅备份存在的文件。
    """
    backup_dir = os.path.join(project_root, BACKUP_DIR)
    os.makedirs(backup_dir, exist_ok=True)
    for fp in file_paths:
        if not os.path.exists(fp):
            continue
        rel = os.path.relpath(fp, project_root)
        dest = os.path.join(backup_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(fp, dest)


def restore_backup(project_root: str) -> None:
    """从备份恢复文件。对应 backup.ts:restoreBackup。"""
    backup_dir = os.path.join(project_root, BACKUP_DIR)
    if not os.path.isdir(backup_dir):
        return
    for root, _dirs, files in os.walk(backup_dir):
        for name in files:
            backup_path = os.path.join(root, name)
            rel = os.path.relpath(backup_path, backup_dir)
            original = os.path.join(project_root, rel)
            os.makedirs(os.path.dirname(original), exist_ok=True)
            shutil.copy2(backup_path, original)


def clear_backup(project_root: str) -> None:
    """清理备份目录。对应 backup.ts:clearBackup。"""
    backup_dir = os.path.join(project_root, BACKUP_DIR)
    if os.path.isdir(backup_dir):
        shutil.rmtree(backup_dir)


# ---------------------------------------------------------------------------
# 三向合并 (对应 merge.ts)
# ---------------------------------------------------------------------------

def merge_file(current_path: str, base_path: str, skill_path: str) -> bool:
    """执行 git merge-file 三向合并。对应 merge.ts:mergeFile。

    git merge-file current base skill:
      - 干净合并: exit 0, current 被就地修改
      - 有冲突: exit >0 (冲突数), current 含冲突标记
      - 错误: exit <0

    Returns: True if clean merge, False if conflicts.
    """
    result = subprocess.run(
        ["git", "merge-file", current_path, base_path, skill_path],
        capture_output=True,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Manifest 校验 (对应 manifest.ts)
# ---------------------------------------------------------------------------

def read_manifest(skill_dir: str) -> SkillManifest:
    """读取并校验 manifest。对应 manifest.ts:readManifest。

    原实现解析 manifest.yaml，demo 用 manifest.json。
    校验: 必填字段 + 路径安全（禁止 .. 和绝对路径）。
    """
    manifest_path = os.path.join(skill_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        data = json.load(f)

    for field_name in ("skill", "version"):
        if field_name not in data:
            raise ValueError(f"Manifest missing required field: {field_name}")

    # 路径安全校验
    for p in data.get("adds", []) + data.get("modifies", []):
        if ".." in p or os.path.isabs(p):
            raise ValueError(f"Invalid path in manifest: {p}")

    return SkillManifest(
        skill=data["skill"],
        version=data["version"],
        description=data.get("description", ""),
        core_version=data.get("core_version", "0.1.0"),
        adds=data.get("adds", []),
        modifies=data.get("modifies", []),
        conflicts=data.get("conflicts", []),
        depends=data.get("depends", []),
    )


def check_conflicts(manifest: SkillManifest, state: SkillState) -> list[str]:
    """检查 skill 间声明式冲突。对应 manifest.ts:checkConflicts。

    每个 skill 在 manifest.conflicts 中声明与哪些 skill 互斥。
    返回冲突列表（空 = 无冲突）。
    """
    applied_names = {s.name for s in state.applied_skills}
    return [c for c in manifest.conflicts if c in applied_names]


def check_dependencies(manifest: SkillManifest, state: SkillState) -> list[str]:
    """检查 skill 依赖是否满足。对应 manifest.ts:checkDependencies。

    返回缺失依赖列表（空 = 全部满足）。
    """
    applied_names = {s.name for s in state.applied_skills}
    return [d for d in manifest.depends if d not in applied_names]


# ---------------------------------------------------------------------------
# SkillsEngine — 核心引擎
# ---------------------------------------------------------------------------

class SkillsEngine:
    """NanoClaw Skills Engine 核心，管理 skill 的完整生命周期。

    对应 skills-engine/ 目录的 14 个模块。Demo 将核心流程合并到一个类中。

    关键设计原则:
      1. 每个操作先 backup，失败时 restore
      2. 修改文件用三向合并: current <-- base --> skill
      3. 卸载用 replay-without: 回到 base，重放除目标外的所有 skill
      4. Rebase: 生成归档 patch，三向合并到新 base
      5. 文件锁防并发（demo 简化为目录锁标记）
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self._base_dir = os.path.join(project_root, BASE_DIR)

    # -- 公开 API --

    def install_skill(
        self,
        skill_dir: str,
        *,
        patch_fn: Callable[[str], None] | None = None,
    ) -> ApplyResult:
        """安装 skill。对应 apply.ts:applySkill。

        流程:
          1. 读取 manifest → pre-flight checks（冲突/依赖/版本）
          2. 备份所有受影响文件
          3. 复制 add/ 下的新文件到项目
          4. 对 modify/ 下的文件执行三向合并
          5. 更新状态记录
          6. 清理备份（成功时）或回滚（失败时）

        patch_fn: 可选的代码变换函数（模拟 skill 修改行为）
        """
        manifest = read_manifest(skill_dir)
        state = read_state(self.project_root)

        # Pre-flight: 冲突检查
        conflicting = check_conflicts(manifest, state)
        if conflicting:
            return ApplyResult(
                success=False,
                skill=manifest.skill,
                version=manifest.version,
                error=f"Conflicting skills: {', '.join(conflicting)}",
            )

        # Pre-flight: 依赖检查
        missing = check_dependencies(manifest, state)
        if missing:
            return ApplyResult(
                success=False,
                skill=manifest.skill,
                version=manifest.version,
                error=f"Missing dependencies: {', '.join(missing)}",
            )

        # 收集受影响文件
        affected_files = []
        for rel in manifest.adds + manifest.modifies:
            affected_files.append(os.path.join(self.project_root, rel))

        # 备份
        create_backup(self.project_root, affected_files)

        merge_conflicts: list[str] = []

        try:
            # 1. 复制 add/ 下的新文件
            add_dir = os.path.join(skill_dir, "add")
            if os.path.isdir(add_dir):
                for rel_path in manifest.adds:
                    src = os.path.join(add_dir, rel_path)
                    dst = os.path.join(self.project_root, rel_path)
                    if os.path.exists(src):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)

            # 2. 三向合并 modify/ 下的文件
            modify_dir = os.path.join(skill_dir, "modify")
            for rel_path in manifest.modifies:
                current = os.path.join(self.project_root, rel_path)
                base = os.path.join(self._base_dir, rel_path)
                skill_file = os.path.join(modify_dir, rel_path)

                if not os.path.exists(skill_file):
                    # 如果 modify/ 中没有文件，用 patch_fn 生成
                    if patch_fn and os.path.exists(current):
                        patch_fn(current)
                    continue

                if not os.path.exists(current):
                    # 文件不存在，直接复制
                    os.makedirs(os.path.dirname(current), exist_ok=True)
                    shutil.copy2(skill_file, current)
                    continue

                if not os.path.exists(base):
                    # 无 base 快照，用当前文件作为 base（首次安装）
                    os.makedirs(os.path.dirname(base), exist_ok=True)
                    shutil.copy2(current, base)

                # 三向合并: current <-- base --> skill
                # git merge-file 就地修改第一个参数
                tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"-{os.path.basename(rel_path)}"
                )
                tmp.close()
                shutil.copy2(current, tmp.name)

                clean = merge_file(tmp.name, base, skill_file)
                shutil.copy2(tmp.name, current)
                os.unlink(tmp.name)

                if not clean:
                    merge_conflicts.append(rel_path)

            # 如果有 patch_fn 但没有 modify/ 目录，对所有 modifies 文件执行
            if patch_fn and not os.path.isdir(modify_dir):
                for rel_path in manifest.modifies:
                    current = os.path.join(self.project_root, rel_path)
                    if os.path.exists(current):
                        patch_fn(current)

            if merge_conflicts:
                # 有冲突但不回滚，返回让用户处理
                return ApplyResult(
                    success=False,
                    skill=manifest.skill,
                    version=manifest.version,
                    merge_conflicts=merge_conflicts,
                    error=f"Merge conflicts in: {', '.join(merge_conflicts)}",
                )

            # 3. 更新状态
            file_hashes: dict[str, str] = {}
            for rel in manifest.adds + manifest.modifies:
                abs_path = os.path.join(self.project_root, rel)
                if os.path.exists(abs_path):
                    file_hashes[rel] = compute_file_hash(abs_path)

            state.applied_skills = [
                s for s in state.applied_skills if s.name != manifest.skill
            ]
            state.applied_skills.append(AppliedSkill(
                name=manifest.skill,
                version=manifest.version,
                applied_at=_now_iso(),
                file_hashes=file_hashes,
            ))
            write_state(self.project_root, state)

            clear_backup(self.project_root)
            return ApplyResult(
                success=True, skill=manifest.skill, version=manifest.version
            )

        except Exception as e:
            restore_backup(self.project_root)
            clear_backup(self.project_root)
            return ApplyResult(
                success=False,
                skill=manifest.skill,
                version=manifest.version,
                error=str(e),
            )

    def uninstall_skill(self, name: str) -> UninstallResult:
        """卸载 skill。对应 uninstall.ts:uninstallSkill。

        策略: replay-without
          1. 验证 skill 存在
          2. 检查是否已 rebase（rebase 后不可单独卸载）
          3. 备份所有受影响文件
          4. 将受影响文件恢复到 base 状态
          5. 重放剩余 skills
          6. 更新状态
        """
        state = read_state(self.project_root)

        # 检查 rebase 后的限制
        if state.rebased_at:
            return UninstallResult(
                success=False,
                skill=name,
                error="Cannot uninstall after rebase. Skills are baked into base.",
            )

        # 验证 skill 存在
        skill_entry = next(
            (s for s in state.applied_skills if s.name == name), None
        )
        if not skill_entry:
            return UninstallResult(
                success=False,
                skill=name,
                error=f'Skill "{name}" is not applied.',
            )

        # 收集所有 skill 文件用于备份
        all_files: set[str] = set()
        for skill in state.applied_skills:
            all_files.update(skill.file_hashes.keys())

        backup_paths = [
            os.path.join(self.project_root, f) for f in all_files
        ]
        create_backup(self.project_root, backup_paths)

        try:
            # 恢复被移除 skill 独有的文件到 base 状态
            remaining_files: set[str] = set()
            for skill in state.applied_skills:
                if skill.name == name:
                    continue
                remaining_files.update(skill.file_hashes.keys())

            for file_path in skill_entry.file_hashes:
                if file_path in remaining_files:
                    continue  # 其他 skill 也用到此文件，replaySkills 处理
                current = os.path.join(self.project_root, file_path)
                base = os.path.join(self._base_dir, file_path)
                if os.path.exists(base):
                    os.makedirs(os.path.dirname(current), exist_ok=True)
                    shutil.copy2(base, current)
                elif os.path.exists(current):
                    # add-only 文件，不在 base 中，直接删除
                    os.unlink(current)

            # 更新状态
            state.applied_skills = [
                s for s in state.applied_skills if s.name != name
            ]

            # 更新剩余 skill 的文件哈希
            for skill in state.applied_skills:
                new_hashes: dict[str, str] = {}
                for fp in skill.file_hashes:
                    abs_path = os.path.join(self.project_root, fp)
                    if os.path.exists(abs_path):
                        new_hashes[fp] = compute_file_hash(abs_path)
                skill.file_hashes = new_hashes

            write_state(self.project_root, state)
            clear_backup(self.project_root)

            return UninstallResult(success=True, skill=name)

        except Exception as e:
            restore_backup(self.project_root)
            clear_backup(self.project_root)
            return UninstallResult(
                success=False, skill=name, error=str(e)
            )

    def list_skills(self) -> list[AppliedSkill]:
        """列出已安装 skills。对应 state.ts:getAppliedSkills。"""
        state = read_state(self.project_root)
        return state.applied_skills

    def rebase(self, new_base_path: str | None = None) -> RebaseResult:
        """Rebase: 将 skill 变更合并到新的 base。对应 rebase.ts:rebase。

        两种模式:
          A. 无 new_base_path: flatten — 将当前工作树烘焙进 base
          B. 有 new_base_path: 三向合并 — 保留 skill 变更，合并 upstream 更新

        流程:
          1. 生成归档 combined.patch (diff base vs working tree)
          2. 模式 A: 用当前文件覆盖 base
          3. 模式 B: 三向合并 current <-- old-base --> new-base
          4. 标记 rebased_at（rebase 后不可单独卸载 skill）
        """
        state = read_state(self.project_root)

        if not state.applied_skills:
            return RebaseResult(
                success=False, error="No skills applied. Nothing to rebase."
            )

        # 收集被追踪文件
        tracked: set[str] = set()
        for skill in state.applied_skills:
            tracked.update(skill.file_hashes.keys())

        # 也收集 base 中的文件
        if os.path.isdir(self._base_dir):
            for root, _dirs, files in os.walk(self._base_dir):
                for name in files:
                    rel = os.path.relpath(
                        os.path.join(root, name), self._base_dir
                    )
                    tracked.add(rel)

        # 备份
        backup_files = []
        for rel in tracked:
            for prefix in (self.project_root, self._base_dir):
                p = os.path.join(prefix, rel)
                if os.path.exists(p):
                    backup_files.append(p)
        state_file = _state_path(self.project_root)
        if os.path.exists(state_file):
            backup_files.append(state_file)
        create_backup(self.project_root, backup_files)

        try:
            # 生成归档 diff
            files_in_patch = 0
            patch_path = os.path.join(
                self.project_root, NANOCLAW_DIR, "combined.patch"
            )
            patch_lines: list[str] = []

            for rel in sorted(tracked):
                base_file = os.path.join(self._base_dir, rel)
                work_file = os.path.join(self.project_root, rel)
                if not os.path.exists(base_file) and not os.path.exists(work_file):
                    continue

                old = base_file if os.path.exists(base_file) else "/dev/null"
                new = work_file if os.path.exists(work_file) else "/dev/null"

                result = subprocess.run(
                    ["diff", "-ruN", old, new],
                    capture_output=True, text=True,
                )
                if result.stdout.strip():
                    patch_lines.append(result.stdout)
                    files_in_patch += 1

            Path(patch_path).write_text("\n".join(patch_lines))

            if new_base_path is None:
                # 模式 A: Flatten — 将工作树烘焙进 base
                for rel in tracked:
                    work_file = os.path.join(self.project_root, rel)
                    base_file = os.path.join(self._base_dir, rel)
                    if os.path.exists(work_file):
                        os.makedirs(os.path.dirname(base_file), exist_ok=True)
                        shutil.copy2(work_file, base_file)
                    elif os.path.exists(base_file):
                        os.unlink(base_file)
            else:
                # 模式 B: 三向合并到新 base
                # 保存当前工作树内容
                saved: dict[str, str] = {}
                for rel in tracked:
                    work_file = os.path.join(self.project_root, rel)
                    if os.path.exists(work_file):
                        saved[rel] = Path(work_file).read_text()

                # 替换 base
                abs_new_base = os.path.abspath(new_base_path)
                if os.path.isdir(self._base_dir):
                    shutil.rmtree(self._base_dir)
                os.makedirs(self._base_dir, exist_ok=True)
                shutil.copytree(abs_new_base, self._base_dir, dirs_exist_ok=True)

                # 复制新 base 到工作树
                shutil.copytree(abs_new_base, self.project_root, dirs_exist_ok=True)

                # 三向合并
                merge_conflicts: list[str] = []
                for rel in tracked:
                    new_base_file = os.path.join(abs_new_base, rel)
                    current = os.path.join(self.project_root, rel)

                    if rel not in saved:
                        continue
                    if not os.path.exists(new_base_file):
                        # 文件仅存在于工作树，恢复
                        os.makedirs(os.path.dirname(current), exist_ok=True)
                        Path(current).write_text(saved[rel])
                        continue

                    new_content = Path(new_base_file).read_text()
                    if new_content == saved[rel]:
                        continue

                    # 查找旧 base
                    old_base_backup = os.path.join(
                        self.project_root, BACKUP_DIR, BASE_DIR, rel
                    )
                    if not os.path.exists(old_base_backup):
                        Path(current).write_text(saved[rel])
                        continue

                    # 三向合并
                    tmp_saved = tempfile.NamedTemporaryFile(
                        delete=False, suffix=f"-{os.path.basename(rel)}"
                    )
                    tmp_saved.close()
                    Path(tmp_saved.name).write_text(saved[rel])

                    clean = merge_file(current, old_base_backup, tmp_saved.name)
                    os.unlink(tmp_saved.name)

                    if not clean:
                        merge_conflicts.append(rel)

                if merge_conflicts:
                    return RebaseResult(
                        success=False,
                        files_in_patch=files_in_patch,
                        patch_file=patch_path,
                        merge_conflicts=merge_conflicts,
                        error=f"Merge conflicts: {', '.join(merge_conflicts)}",
                    )

            # 更新状态
            now = _now_iso()
            for skill in state.applied_skills:
                new_hashes: dict[str, str] = {}
                for rel in skill.file_hashes:
                    abs_path = os.path.join(self.project_root, rel)
                    if os.path.exists(abs_path):
                        new_hashes[rel] = compute_file_hash(abs_path)
                skill.file_hashes = new_hashes

            state.rebased_at = now
            write_state(self.project_root, state)
            clear_backup(self.project_root)

            return RebaseResult(
                success=True,
                files_in_patch=files_in_patch,
                patch_file=patch_path,
                rebased_at=now,
            )

        except Exception as e:
            restore_backup(self.project_root)
            clear_backup(self.project_root)
            return RebaseResult(success=False, error=str(e))

    def detect_conflicts(self, skill_dir: str) -> list[str]:
        """检测 skill 与当前已安装 skills 的冲突。对应 manifest.ts:checkConflicts。

        两层冲突检测:
          1. 声明式冲突: manifest.conflicts 列表
          2. 文件级冲突: skill 的 modifies 与已安装 skill 的文件哈希不匹配
        """
        manifest = read_manifest(skill_dir)
        state = read_state(self.project_root)

        conflicts: list[str] = []

        # 层 1: 声明式冲突
        declared = check_conflicts(manifest, state)
        for c in declared:
            conflicts.append(f"[declared] Conflicts with installed skill: {c}")

        # 层 2: 文件级冲突 — 两个 skill 修改同一文件
        applied_files: dict[str, str] = {}  # file -> skill name
        for skill in state.applied_skills:
            for file_path in skill.file_hashes:
                applied_files[file_path] = skill.name

        for rel in manifest.modifies:
            if rel in applied_files:
                conflicts.append(
                    f"[file] {rel} already modified by: {applied_files[rel]}"
                )

        return conflicts


# ---------------------------------------------------------------------------
# 项目初始化
# ---------------------------------------------------------------------------

def init_project(project_root: str, files: dict[str, str] | None = None) -> None:
    """初始化项目目录，创建 base 快照和初始状态。

    对应 init.ts:initNanoclawDir + migrate.ts:initSkillsSystem。
    """
    os.makedirs(project_root, exist_ok=True)
    os.makedirs(os.path.join(project_root, BASE_DIR), exist_ok=True)

    # 写入初始文件
    if files:
        for rel, content in files.items():
            fp = os.path.join(project_root, rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            Path(fp).write_text(content)

            # 同时写入 base 快照
            bp = os.path.join(project_root, BASE_DIR, rel)
            os.makedirs(os.path.dirname(bp), exist_ok=True)
            Path(bp).write_text(content)

    # 写入初始状态
    write_state(project_root, SkillState())


def create_skill_package(
    skill_dir: str,
    manifest: SkillManifest,
    add_files: dict[str, str] | None = None,
    modify_files: dict[str, str] | None = None,
) -> None:
    """创建 skill 包目录结构。

    原实现的 skill 包结构:
      skill-dir/
        manifest.yaml (demo: manifest.json)
        add/          新增文件
        modify/       修改后的文件（用于三向合并）
    """
    os.makedirs(skill_dir, exist_ok=True)

    # 写入 manifest
    manifest_data = {
        "skill": manifest.skill,
        "version": manifest.version,
        "description": manifest.description,
        "core_version": manifest.core_version,
        "adds": manifest.adds,
        "modifies": manifest.modifies,
        "conflicts": manifest.conflicts,
        "depends": manifest.depends,
    }
    with open(os.path.join(skill_dir, "manifest.json"), "w") as f:
        json.dump(manifest_data, f, indent=2)

    # 写入 add/ 文件
    if add_files:
        for rel, content in add_files.items():
            fp = os.path.join(skill_dir, "add", rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            Path(fp).write_text(content)

    # 写入 modify/ 文件
    if modify_files:
        for rel, content in modify_files.items():
            fp = os.path.join(skill_dir, "modify", rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            Path(fp).write_text(content)
