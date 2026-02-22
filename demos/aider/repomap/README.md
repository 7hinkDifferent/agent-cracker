# Demo: Aider — 仓库语法地图（RepoMap）

## 目标

用最简代码复现 Aider 的 RepoMap 机制：tree-sitter 代码解析 → 依赖图构建 → PageRank 排序 → token 约束输出。

## 原理

Aider 面临的核心问题是：如何让 LLM 理解整个代码库的结构，而不超出 context window？RepoMap 的解决方案是构建一张**仓库语法地图**。

工作流程：
1. **tree-sitter 解析**：用 tree-sitter 解析所有源文件，提取代码符号（函数名、类名等）及其类型（定义 or 引用）
2. **构建依赖图**：如果文件 A 引用了文件 B 中定义的标识符，就创建一条 A→B 的边。当前聊天中的文件引用权重放大 50 倍——这是 Aider 的关键洞察，确保地图聚焦于用户当前工作相关的代码
3. **PageRank 排序**：用 PageRank 算法对文件/标识符进行重要性排序，被引用最多的核心文件自然排名靠前
4. **Token 约束输出**：按排名输出定义列表，直到达到 token 预算上限

## 运行

```bash
cd demos/aider/repomap
pip install -r requirements.txt
python repomap.py
```

## 文件结构

```
demos/aider/repomap/
├── README.md           # 本文件
├── requirements.txt    # tree-sitter, networkx
├── repomap.py          # 核心实现
└── sample_project/     # 示例项目
    ├── app.py          # 主应用（引用 models + utils）
    ├── models.py       # 数据模型（引用 utils）
    └── utils.py        # 工具函数（被其他文件引用）
```

## 关键代码解读

### 核心算法（5 步）

```python
def build_repo_map(directory, chat_files=None, max_tokens=1024):
    # 1. tree-sitter 解析所有 .py → Tag(file, name, kind=def|ref, line)
    # 2. 构建 defines{ident→files} 和 references{ident→files}
    # 3. 构建 networkx MultiDiGraph，chat_files 引用权重 50x
    # 4. PageRank 排序
    # 5. 输出排名最高的定义，直到达到 token 上限
```

### 50x 权重的意义

当用户正在编辑 `app.py` 时，`app.py` 中引用的所有标识符对应的定义文件（如 `models.py`, `utils.py`）获得 50 倍权重。这使得 RepoMap 自动聚焦于与用户当前工作最相关的代码。

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 语言支持 | 30+ 语言（通过 tree-sitter-language-pack） | 仅 Python |
| 缓存 | SQLite 缓存 tag 结果 | 无缓存 |
| 输出格式 | TreeContext 渲染（含上下文行和折叠） | 简单的 "行号 │ 名称" |
| Token 估算 | tiktoken 精确计算 | 简单的 chars/4 估算 |
| 图算法 | 同样使用 networkx PageRank | 相同 |

## 相关文档

- 分析文档: [docs/aider.md](../../../docs/aider.md)
- 原项目: https://github.com/Aider-AI/aider
- 核心源码: `aider/repomap.py`
