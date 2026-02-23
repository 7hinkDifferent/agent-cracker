# Demo: Aider — LLM Response Parsing（LLM 响应解析）

## 目标

用最简代码复现 Aider 从 LLM 自由文本响应中提取结构化编辑指令的多格式解析机制。

## MVP 角色

LLM 响应解析是连接"LLM 输出"和"文件编辑"的桥梁——将自由文本中的代码修改意图转化为可执行的结构化编辑操作。

## 原理

Aider 支持多种编辑格式，每种格式有独立的解析器。解析器从 LLM 的自由文本响应中提取结构化的编辑指令：

### 多格式适配器模式

```
LLM Response (free text)
    │
    ▼
parse_response(text, format)    ← 统一入口
    │
    ├─ EditBlockParser          ← SEARCH/REPLACE 块格式（默认）
    ├─ WholeFileParser          ← 整文件替换格式
    └─ UnifiedDiffParser        ← unified diff 格式
    │
    ▼
List[Edit] + List[Error]        ← 结构化输出
    │
    ▼
apply / generate_reflection     ← 应用或生成反思反馈
```

### 三种格式对比

| 格式 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| EditBlock (SEARCH/REPLACE) | 精确局部修改 | Token 高效，精确定位 | 依赖精确匹配 |
| WholeFile | 新文件或大改 | 简单直接 | Token 浪费 |
| UnifiedDiff | 复杂多处修改 | 标准 diff 格式 | LLM 容易出错 |

### 解析失败 → 反思循环

当 SEARCH 块无法匹配文件内容时，解析器生成详细的错误信息反馈给 LLM：

```
"# 1 edit(s) failed!
SEARCH block failed in calculator.py:
  Search text not found: def dividee(self, a, b)...
  Did you mean: def divide(self, a, b):
Please review and retry."
```

这个反馈消息会作为 `reflected_message` 触发反思循环（参见 core-loop demo）。

## 运行

```bash
cd demos/aider/llm-response-parsing
python main.py
```

无外部依赖，仅使用 Python 标准库。

## 文件结构

```
demos/aider/llm-response-parsing/
├── README.md       # 本文件
└── main.py         # 三种格式解析器 + 反思反馈生成
```

## 关键代码解读

### 格式适配器模式（工厂 + 多态）

```python
class BaseParser:
    def get_edits(self, response_text, valid_fnames=None):
        raise NotImplementedError

class EditBlockParser(BaseParser):   # SEARCH/REPLACE
    ...
class WholeFileParser(BaseParser):   # 整文件
    ...
class UnifiedDiffParser(BaseParser): # unified diff
    ...

# 注册表
PARSERS = {
    "editblock": EditBlockParser(),
    "wholefile": WholeFileParser(),
    "udiff":     UnifiedDiffParser(),
}
```

### SEARCH/REPLACE 块提取（核心正则）

```python
HEAD_PAT    = re.compile(r"^<{5,9} SEARCH>?\s*$")   # <<<<<<< SEARCH
DIVIDER_PAT = re.compile(r"^={5,9}\s*$")             # =======
UPDATED_PAT = re.compile(r"^>{5,9} REPLACE\s*$")     # >>>>>>> REPLACE
```

括号数量 5-9 是为了容忍 LLM 输出变体（可能多写或少写几个）。

### 文件名模糊匹配

```python
def _match_filename(candidate, valid_fnames):
    # 1. 精确匹配
    if candidate in valid_fnames: return candidate
    # 2. basename 匹配
    for fname in valid_fnames:
        if basename(fname) == basename(candidate): return fname
    # 3. 80% 相似度模糊匹配
    matches = get_close_matches(candidate, valid_fnames, cutoff=0.8)
    if matches: return matches[0]
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 格式数量 | 6+ 种（EditBlock/Whole/Udiff/Patch/Architect/Ask） | 3 种（EditBlock/Whole/Udiff） |
| EditBlock 解析 | 支持连续块、shell 命令提取、lookahead 消歧 | 基础状态机 |
| 匹配容错 | 5 级（精确→空白→省略号→编辑距离→跨文件） | 仅精确匹配 |
| 文件名查找 | 3 行回溯 + strip + fuzzy + 上一块继承 | 3 行回溯 + fuzzy |
| 错误反馈 | 包含相似行提示、已存在检查、多文件尝试 | 简化版相似行提示 |
| function calling | 支持 JSON Schema 格式的函数调用 | 不支持 |

## 相关文档

- 分析文档: [docs/aider.md](../../../docs/aider.md)
- 原项目: https://github.com/Aider-AI/aider
- 基于 commit: `7afaa26`
- 核心源码: `aider/coders/editblock_coder.py`（find_original_update_blocks）、`aider/coders/base_coder.py`（apply_updates）
