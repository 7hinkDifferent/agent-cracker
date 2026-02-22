# Demo: Aider — SEARCH/REPLACE 解析器

## 目标

用最简代码复现 Aider 的 SEARCH/REPLACE 编辑块解析与应用机制。

## 原理

Aider 让 LLM 用一种特殊格式输出代码修改——SEARCH/REPLACE 块。LLM 先写出需要被替换的**原始代码**（SEARCH），再写出**修改后的代码**（REPLACE）。这种格式比输出整个文件高效得多，也更精确。

解析器（parser）从 LLM 的自由文本输出中提取这些结构化编辑块。替换器（replacer）将编辑应用到实际文件，支持两级匹配：精确匹配和空白容忍匹配。空白容忍匹配允许 LLM 输出的缩进与实际文件略有差异——这在实际使用中非常常见。

核心格式：
```
path/to/file.py
<<<<<<< SEARCH
原始代码
=======
修改后代码
>>>>>>> REPLACE
```

## 运行

```bash
cd demos/aider/search-replace
python main.py
```

无外部依赖，仅使用 Python 标准库。

## 文件结构

```
demos/aider/search-replace/
├── README.md       # 本文件
├── main.py         # 交互入口 + 示例 LLM 输出
├── parser.py       # SEARCH/REPLACE 块解析（状态机）
└── replacer.py     # 模糊匹配 + 文件应用
```

## 关键代码解读

### 解析器（parser.py）

状态机逐行扫描 LLM 输出，使用正则匹配三个标记：

```python
HEAD_PAT    = re.compile(r"^<{5,9} SEARCH\s*$")   # <<<<<<< SEARCH
DIVIDER_PAT = re.compile(r"^={5,9}\s*$")           # =======
UPDATED_PAT = re.compile(r"^>{5,9} REPLACE\s*$")   # >>>>>>> REPLACE
```

流程：发现 HEAD → 向上查找文件名 → 收集 SEARCH 内容 → 遇到 DIVIDER → 收集 REPLACE 内容 → 遇到 UPDATED → 输出 EditBlock。

### 替换器（replacer.py）

两级匹配策略：
1. **Tier 1 精确匹配**：`search_text in content`，直接替换
2. **Tier 2 空白容忍**：去除行尾空白和首尾空行后匹配，替换时重新计算缩进

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 匹配级别 | 5+ 级（精确→空白→省略号→编辑距离→LLM 补全） | 2 级（精确 + 空白容忍） |
| 文件名解析 | 支持多种格式（带 backtick、路径前缀等） | 简单向上查找 |
| Git 集成 | 自动 commit 修改 | 无 |
| 错误恢复 | 匹配失败可请求 LLM 重试 | 仅打印失败信息 |

## 相关文档

- 分析文档: [docs/aider.md](../../../docs/aider.md)
- 原项目: https://github.com/Aider-AI/aider
- 核心源码: `aider/coders/editblock_coder.py`
