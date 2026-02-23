"""
Aider LLM 响应解析器。

提供多格式适配器（EditBlock / WholeFile / UnifiedDiff）和反思反馈生成，
可被其他 demo（如 mini-aider）导入复用。

核心接口:
  - EditBlockParser / WholeFileParser / UnifiedDiffParser: 格式解析器
  - parse_response(): 统一入口，按格式名选择解析器
  - generate_reflection(): 解析失败时生成反馈消息
"""

import re
from dataclasses import dataclass
from difflib import get_close_matches

# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class EditBlock:
    filename: str
    search_text: str
    replace_text: str


@dataclass
class WholeFileEdit:
    filename: str
    content: str


@dataclass
class UnifiedDiffEdit:
    filename: str
    original_lines: list
    modified_lines: list


# ── 格式适配器基类（多态模式）────────────────────────────────────

class BaseParser:
    """所有格式解析器的基类，对应 Aider 的 Coder 子类多态。"""
    name = "base"

    def get_edits(self, response_text, valid_fnames=None):
        raise NotImplementedError


# ── EditBlock 格式解析器 ─────────────────────────────────────────

class EditBlockParser(BaseParser):
    """
    解析 SEARCH/REPLACE 块格式。
    对应 aider/coders/editblock_coder.py:find_original_update_blocks()
    """
    name = "editblock"

    HEAD_PAT = re.compile(r"^<{5,9} SEARCH>?\s*$")
    DIVIDER_PAT = re.compile(r"^={5,9}\s*$")
    UPDATED_PAT = re.compile(r"^>{5,9} REPLACE\s*$")

    def get_edits(self, response_text, valid_fnames=None):
        edits = []
        errors = []
        lines = response_text.splitlines()
        i = 0

        while i < len(lines):
            if not self.HEAD_PAT.match(lines[i].strip()):
                i += 1
                continue

            filename = self._find_filename(lines, i, valid_fnames)
            i += 1

            # SEARCH 内容收集
            search_lines = []
            while i < len(lines) and not self.DIVIDER_PAT.match(lines[i].strip()):
                search_lines.append(lines[i])
                i += 1

            if i >= len(lines):
                errors.append("Expected ======= divider, but reached end of response")
                break
            i += 1

            # REPLACE 内容收集
            replace_lines = []
            while i < len(lines) and not self.UPDATED_PAT.match(lines[i].strip()):
                if self.DIVIDER_PAT.match(lines[i].strip()):
                    edits.append(EditBlock(filename, "\n".join(search_lines), "\n".join(replace_lines)))
                    search_lines = replace_lines
                    replace_lines = []
                    i += 1
                    continue
                replace_lines.append(lines[i])
                i += 1

            if i >= len(lines):
                errors.append("Expected >>>>>>> REPLACE, but reached end of response")
                break
            i += 1

            edits.append(EditBlock(filename, "\n".join(search_lines), "\n".join(replace_lines)))

        return edits, errors

    def _find_filename(self, lines, search_idx, valid_fnames=None):
        """向上查找文件名。"""
        for j in range(search_idx - 1, max(search_idx - 4, -1), -1):
            candidate = lines[j].strip()
            if candidate.startswith("```"):
                continue
            candidate = candidate.strip("`").strip("*").strip("#").strip(":").strip()
            if not candidate:
                continue
            if "." in candidate or "/" in candidate:
                if valid_fnames:
                    return self._match_filename(candidate, valid_fnames)
                return candidate
        return "<unknown>"

    def _match_filename(self, candidate, valid_fnames):
        """文件名模糊匹配。"""
        if candidate in valid_fnames:
            return candidate
        for fname in valid_fnames:
            if fname.split("/")[-1] == candidate.split("/")[-1]:
                return fname
        matches = get_close_matches(candidate, valid_fnames, n=1, cutoff=0.8)
        if matches:
            return matches[0]
        return candidate


# ── WholeFile 格式解析器 ─────────────────────────────────────────

class WholeFileParser(BaseParser):
    """
    解析整文件输出格式。
    对应 aider/coders/wholefile_coder.py:get_edits()
    """
    name = "wholefile"

    FENCE_PAT = re.compile(r"^```\w*\s*$")

    def get_edits(self, response_text, valid_fnames=None):
        edits = []
        errors = []
        lines = response_text.splitlines()
        i = 0

        while i < len(lines):
            if self.FENCE_PAT.match(lines[i].strip()):
                filename = None
                if i > 0:
                    candidate = lines[i - 1].strip().strip("`").strip("*").strip()
                    if candidate and ("." in candidate or "/" in candidate):
                        filename = candidate

                i += 1
                content_lines = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    content_lines.append(lines[i])
                    i += 1
                i += 1

                if filename:
                    edits.append(WholeFileEdit(filename, "\n".join(content_lines)))
            else:
                i += 1

        return edits, errors


# ── UnifiedDiff 格式解析器 ───────────────────────────────────────

class UnifiedDiffParser(BaseParser):
    """
    解析 unified diff 格式。
    对应 aider/coders/udiff_coder.py:find_diffs()
    """
    name = "udiff"

    DIFF_HEADER = re.compile(r"^---\s+a/(.+)")
    DIFF_HEADER2 = re.compile(r"^\+\+\+\s+b/(.+)")
    HUNK_HEADER = re.compile(r"^@@\s+.*\s+@@")

    def get_edits(self, response_text, valid_fnames=None):
        edits = []
        errors = []
        lines = response_text.splitlines()
        i = 0

        while i < len(lines):
            m = self.DIFF_HEADER.match(lines[i])
            if not m:
                i += 1
                continue

            filename = m.group(1)
            i += 1

            if i < len(lines) and self.DIFF_HEADER2.match(lines[i]):
                i += 1

            original, modified = [], []
            while i < len(lines):
                line = lines[i]
                if self.DIFF_HEADER.match(line):
                    break
                if line.startswith("-"):
                    original.append(line[1:])
                elif line.startswith("+"):
                    modified.append(line[1:])
                elif line.startswith(" "):
                    original.append(line[1:])
                    modified.append(line[1:])
                elif self.HUNK_HEADER.match(line):
                    pass
                else:
                    break
                i += 1

            edits.append(UnifiedDiffEdit(filename, original, modified))

        return edits, errors


# ── 格式注册表（工厂模式）────────────────────────────────────────

PARSERS = {
    "editblock": EditBlockParser(),
    "wholefile": WholeFileParser(),
    "udiff": UnifiedDiffParser(),
}


def parse_response(response_text, format_name="editblock", valid_fnames=None):
    """
    统一入口：选择格式解析器，解析 LLM 响应。
    对应 base_coder.py:apply_updates() → get_edits()
    """
    parser = PARSERS.get(format_name)
    if not parser:
        raise ValueError(f"Unknown format: {format_name}")
    return parser.get_edits(response_text, valid_fnames)


# ── 反思反馈生成 ─────────────────────────────────────────────────

def generate_reflection(edits, errors, file_contents):
    """
    当解析的编辑无法匹配文件时，生成反思反馈消息。
    对应 editblock_coder.py 的 apply_edits() 错误分支。
    """
    failed = []
    for edit in edits:
        if not isinstance(edit, EditBlock):
            continue
        content = file_contents.get(edit.filename, "")
        if edit.search_text and edit.search_text not in content:
            similar = _find_similar_lines(edit.search_text, content)
            msg = f"SEARCH block failed in {edit.filename}:\n"
            msg += f"  Search text not found: {edit.search_text[:80]}...\n"
            if similar:
                msg += f"  Did you mean: {similar}\n"
            failed.append(msg)

    if errors:
        failed.extend(errors)

    if failed:
        return (
            f"# {len(failed)} edit(s) failed!\n\n"
            + "\n".join(failed)
            + "\n\nPlease review and retry with corrected SEARCH/REPLACE blocks."
        )
    return None


def _find_similar_lines(search_text, content):
    """在文件内容中找到与 search_text 最相似的片段。"""
    search_lines = search_text.splitlines()
    if not search_lines:
        return None
    content_lines = content.splitlines()
    first_line = search_lines[0].strip()
    for cl in content_lines:
        if get_close_matches(first_line, [cl.strip()], n=1, cutoff=0.6):
            return cl.strip()
    return None
