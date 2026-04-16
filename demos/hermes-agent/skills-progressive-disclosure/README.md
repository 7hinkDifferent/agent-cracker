# Hermes Agent — skills-progressive-disclosure

## 目标

用最简代码复现 Hermes 的技能渐进加载：**先暴露 skills index，再按需打开正文和 references**。

## 原理

Hermes 不会在每轮开始时把所有 skill 正文都注入 prompt。它会先给模型一个技能索引，让模型知道“有哪些能力可用”；只有当模型显式查看某个 skill 时，才会加载对应 `SKILL.md`；如果还需要更细的材料，再继续读取 references 或 scripts。

这样做能显著降低 token 占用，同时保留技能系统的可扩展性——尤其适合长期运行、技能会不断增长的个人 agent 平台。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/skills-progressive-disclosure/
├── README.md
├── main.py
├── skills_loader.py
└── sample_skills/
    ├── incident-triage/
    │   ├── SKILL.md
    │   └── references/template.md
    └── python-workflow/
        ├── SKILL.md
        └── references/checklist.md
```

## 关键代码解读

```python
print("[Level 0] skills_list()")
for summary in store.list_skills():
    ...

print("[Level 1] skill_view('python-workflow')")
print(store.skill_view("python-workflow"))

print("[Level 2] references for 'incident-triage'")
print(store.load_references("incident-triage"))
```

这 3 个层级对应 Hermes 的核心思想：**索引 → 正文 → 附属资料**。不是一开始全读，而是按需深入。

## 运行后建议观察

1. **Level 0 只暴露索引**：先告诉模型“有哪些技能”，而不是把所有正文塞进 prompt
2. **Level 1 才展开正文**：只有确定要用某个 skill 时才加载 `SKILL.md`
3. **Level 2 再读 references**：模板、脚本、额外材料只在真正需要时读取

这个 demo 还会打印一个粗略的字符载荷，帮助理解渐进加载为什么能省 token。

## 与原实现的差异

- 原版支持 agentskills.io 兼容目录、平台匹配与条件过滤；demo 只保留最小目录结构
- 原版还会处理 frontmatter、禁用技能、脚本执行；demo 只解析 description 并读取 references
- 原版技能会与 prompt builder、memory、cron 协同；demo 单独演示 progressive disclosure

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `agent/skill_utils.py`, `tools/skills_tool.py`, `tools/skill_manager_tool.py`
