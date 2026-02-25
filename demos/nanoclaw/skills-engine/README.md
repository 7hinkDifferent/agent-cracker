# skills-engine -- Skill 安装/卸载/Rebase/冲突检测

## 目标

复现 NanoClaw 的 Skills Engine 核心机制：Skill 安装（三向合并）、卸载（replay-without）、Rebase（烘焙变更到 base）、声明式+文件级冲突检测。

## MVP 角色

Skills Engine 是 NanoClaw 最独特的机制。与传统运行时插件不同，Skill 是**代码变换**——执行后直接修改项目源码。每个 Skill 由 `manifest.yaml` + `add/`（新增文件）+ `modify/`（修改后版本）组成，通过 `git merge-file` 三向合并安全地融入项目。

## 原理

```
Install:
  manifest.yaml → pre-flight checks → backup → copy adds → merge modifies → update state
                   ├─ conflicts?       ├──────────────────────────────────────────→ rollback
                   ├─ depends?         │
                   └─ version?         └→ success → clear backup

Uninstall (replay-without):
  verify skill → backup all → restore base files → remove from state → clear backup

Rebase (flatten):
  collect tracked files → generate combined.patch → copy working tree → base → mark rebased_at
                          (归档记录)                 (烘焙 skill 变更)

Conflict Detection (2 层):
  1. [declared] manifest.conflicts 声明式互斥
  2. [file]     两个 skill 的 modifies 列表有交集

Three-way Merge:
  current ←── base ──→ skill
  (项目当前)  (原始快照) (skill 期望)
  │                      │
  └── git merge-file ───→ 合并结果（或冲突标记）
```

## 运行

```bash
uv run python main.py
```

无外部依赖。使用临时目录隔离，需要系统 `git`（用于 `git merge-file`）。

## 文件结构

```
skills-engine/
├── README.md    # 本文件
├── engine.py    # 可复用模块: SkillsEngine + state/backup/merge/manifest
└── main.py      # Demo 入口（5 个演示场景）
```

## 关键代码解读

### 三向合并（engine.py）

```python
def merge_file(current_path: str, base_path: str, skill_path: str) -> bool:
    result = subprocess.run(
        ["git", "merge-file", current_path, base_path, skill_path],
        capture_output=True,
    )
    return result.returncode == 0  # 0 = clean, >0 = conflict count
```

`git merge-file` 是整个 Skills Engine 的基石。它接受三个文件版本：当前文件、基线快照、skill 期望版本，输出合并结果（或冲突标记）。这让 skill 可以安全修改用户已自定义过的文件。

### 声明式冲突 + 文件级冲突检测（engine.py）

```python
def detect_conflicts(self, skill_dir: str) -> list[str]:
    # 层 1: manifest.conflicts 声明
    declared = check_conflicts(manifest, state)
    # 层 2: modifies 文件与已安装 skill 的 file_hashes 重叠
    for rel in manifest.modifies:
        if rel in applied_files:
            conflicts.append(f"[file] {rel} already modified by: {applied_files[rel]}")
```

两层检测确保在安装前发现问题：声明式冲突由 skill 作者显式声明互斥关系，文件级冲突自动检测同一文件被多个 skill 修改。

### 卸载的 replay-without 策略（engine.py）

```python
def uninstall_skill(self, name: str) -> UninstallResult:
    # 将被移除 skill 独有的文件恢复到 base
    for file_path in skill_entry.file_hashes:
        if file_path in remaining_files:
            continue  # 其他 skill 也用，跳过
        base = os.path.join(self._base_dir, file_path)
        shutil.copy2(base, current)  # 恢复 base 版本
```

原实现用完整的 `replaySkills()` 重放剩余 skill，demo 简化为仅恢复被移除 skill 独有的文件到 base 状态。

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| Manifest 格式 | YAML (`manifest.yaml`) | JSON (`manifest.json`), 避免 pyyaml 依赖 |
| State 格式 | YAML (`state.yaml`) | JSON (`state.json`), 同上 |
| 原子写入 | tmp + rename | 同（`os.replace`） |
| 并发锁 | 文件锁 + PID + stale 检测 | 未实现（demo 为单线程） |
| 卸载策略 | 完整 replaySkills（重放所有剩余 skill） | 简化为恢复 base + 移除 add-only 文件 |
| Rebase 模式 | Flatten + 三向合并 upstream | 仅实现 Flatten |
| Backup | Tombstone 标记 + walk restore | 简化备份/恢复 |
| 结构化操作 | npm deps / env / docker-compose 合并 | 未实现 |
| Path remap | 文件重命名追踪 | 未实现 |
| Post-apply | 执行 shell 命令 + 测试 | 未实现 |
| Customize | 自定义修改 patch 追踪 | 未实现 |

## 相关文档

- 分析文档: [docs/nanoclaw.md -- D12 技能系统](../../docs/nanoclaw.md#12-技能系统与自定义平台维度)
- Skills Engine 概述: [docs/nanoclaw.md -- D7 进阶机制](../../docs/nanoclaw.md#7-进阶机制与独特设计)
- 原始源码: `projects/nanoclaw/skills-engine/` (2,927 行, 14 模块)
  - `apply.ts` (357 行): skill 安装核心
  - `uninstall.ts` (232 行): replay-without 卸载
  - `rebase.ts` (264 行): upstream rebase
  - `manifest.ts` (100 行): manifest 校验 + 冲突/依赖检查
  - `state.ts` (116 行): 状态持久化
  - `merge.ts` (40 行): git merge-file 封装
  - `replay.ts` (271 行): skill 重放引擎
  - `types.ts` (116 行): 类型定义
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
