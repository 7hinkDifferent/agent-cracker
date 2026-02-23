# multi-coder — 多 Coder 多态架构

复现 Aider 的工厂模式 + 多态继承架构：12+ 编辑格式运行时切换。

> Based on commit: [`7afaa26`](https://github.com/Aider-AI/aider/tree/7afaa26f8b8b7b56146f0674d2a67e795b616b7c) (2026-02-22)

## 运行

```bash
uv run python main.py
```

## Demo 内容

| Demo | 说明 |
|------|------|
| Factory Pattern | Coder.create(edit_format) → 7 种子类实例化 |
| Edit Formats | EditBlock/Ask/Architect 不同行为对比 |
| EditBlock Parsing | SEARCH/REPLACE 块提取与应用 |
| Runtime Switch | SwitchCoder 异常触发 Coder 动态切换 |
| Polymorphism | 多态继承结构展示 |

## 核心机制

```
Coder.create(edit_format)     ← 工厂方法
    ├── EditBlockCoder        ← SEARCH/REPLACE（默认）
    ├── WholeFileCoder        ← 整文件替换
    ├── PatchCoder            ← V4A diff
    ├── ArchitectCoder        ← 双模型协作
    ├── AskCoder              ← 纯问答
    ├── ContextCoder          ← 智能文件选择
    └── UdiffCoder            ← Unified diff

三层循环中的切换:
    while True:                    # 外层: 模型/格式切换
      try:
        coder.run()                # 中层: REPL 循环
      except SwitchCoder:
        coder = Coder.create(...)  # 创建新 Coder
```

## 核心源码

| 机制 | 原始文件 |
|------|----------|
| 工厂方法 | `aider/coders/__init__.py` + `base_coder.py` |
| 各编辑格式 | `aider/coders/*_coder.py` |
| SwitchCoder 异常 | `aider/main.py` 外层循环 |
