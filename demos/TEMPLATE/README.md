# Demo: {{AGENT_NAME}} — {{MECHANISM}}

## 目标

用最简代码复现 {{AGENT_NAME}} 的 {{MECHANISM}} 机制。

## MVP 角色

<!-- MVP 组件必填；进阶机制可删除此节 -->
<!-- 说明该组件在 MVP 中的角色：如"主循环"、"Tool 分发"、"Prompt 组装"等 -->

## 原理

<!-- 简述要复现的机制在原 agent 中是如何工作的 -->

## 运行

<!-- 按语言选择对应命令 -->

**Python:**
```bash
uv run --with <deps> python main.py
```

**TypeScript:**
```bash
npx tsx main.ts
```

**Rust:**
```bash
cargo run
```

## 为何选择此语言

<!-- 非 Python demo 必填；Python demo 可删除此节 -->
<!-- 说明该机制为何必须用原生语言复现（如 async runtime、类型系统、FFI、平台 API 等） -->

## 文件结构

**Python:**
```
demos/{{AGENT_NAME}}/{{MECHANISM}}/
├── README.md           # 本文件
├── main.py             # 入口文件
├── requirements.txt    # 外部依赖（可选）
└── config.yaml         # 配置（可选）
```

**TypeScript:**
```
demos/{{AGENT_NAME}}/{{MECHANISM}}/
├── README.md           # 本文件
├── main.ts             # 入口文件
├── package.json        # 依赖声明
└── tsconfig.json       # TypeScript 配置
```

**Rust:**
```
demos/{{AGENT_NAME}}/{{MECHANISM}}/
├── README.md           # 本文件
├── Cargo.toml          # 项目配置与依赖
└── src/
    └── main.rs         # 入口文件
```

## 关键代码解读

<!-- 贴出核心代码并加注释解释 -->

## 与原实现的差异

<!-- 说明简化了哪些部分，保留了哪些核心逻辑 -->

## 相关文档

- 分析文档: [docs/{{AGENT_NAME}}.md](../../../docs/{{AGENT_NAME}}.md)
- 原项目: {{REPO_URL}}
- 基于 commit: `{{COMMIT_SHORT}}`
- 核心源码: `{{SOURCE_PATH}}`
