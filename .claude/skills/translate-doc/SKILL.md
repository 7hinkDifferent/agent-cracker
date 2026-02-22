---
name: translate-doc
description: Translate analysis documents between Chinese and English while preserving markdown formatting and code blocks
---

# Translate Doc

Translate documentation files between Chinese and English. Designed for the analysis documents in `docs/`.

## Trigger

`/translate-doc <file-path>`

## Translation Rules

### Language Detection & Direction

- If the document is primarily in Chinese → translate to English
- If the document is primarily in English → translate to Chinese
- Output file: `<original-name>.<target-lang>.md` (e.g., `aider.en.md` or `aider.zh.md`)

### Preserve Unchanged

These elements must NOT be translated:

1. **Code blocks** (``` fenced blocks) — keep all code as-is
2. **Inline code** (`backtick` content) — keep as-is
3. **File paths** and **URLs** — keep as-is
4. **Technical identifiers** — variable names, function names, class names, CLI flags
5. **Mermaid/ASCII diagrams** — keep as-is
6. **YAML frontmatter** — keep as-is
7. **Table structure** — translate cell content, keep `|` and `-` formatting

### Translation Quality

- Maintain the same heading hierarchy (`#`, `##`, `###`, etc.)
- Keep the same section numbering
- Preserve markdown formatting (bold, italic, lists, links)
- Use natural, idiomatic language in the target language
- For technical terms, provide the translation with the original in parentheses on first occurrence (e.g., "上下文窗口 (Context Window)")

## Steps

1. Read the source file
2. Detect primary language
3. Translate following the rules above
4. Write the translated file alongside the original
5. Report: source file, target file, language direction
