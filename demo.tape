# VHS tape file for recording demo GIF
# Install: brew install vhs
# Run: cd agent-cracker && vhs demo.tape
# Output: demo.gif

Output demo.gif

Set Shell "zsh"
Set FontSize 15
Set Width 900
Set Height 550
Set Theme "Dracula"
Set Padding 20
Set TypingSpeed 40ms

# Show project
Type "echo '=== Agent Cracker: 拆解 Coding Agent 的核心机制 ==='"
Enter
Sleep 1.5s

Type "echo ''"
Enter

# Demo 1: search-replace parser
Type "echo '▸ Demo 1: SEARCH/REPLACE 块解析器 (100 行复现 aider 的编辑机制)'"
Enter
Sleep 1s

Type "cd demos/aider/search-replace && uv run python main.py"
Enter
Sleep 6s

Type "echo ''"
Enter
Sleep 500ms

# Demo 2: prompt assembly
Type "echo '▸ Demo 2: Prompt 组装引擎 (ChatChunks 8 段消息拼接)'"
Enter
Sleep 1s

Type "cd ../prompt-assembly && uv run python main.py 2>&1 | head -30"
Enter
Sleep 5s

Type "echo ''"
Enter
Sleep 500ms

# Summary
Type "echo '✓ 每个 demo 都是 100-200 行的独立可运行最小复现'"
Enter
Sleep 500ms

Type "echo '✓ 已覆盖 3 个 agent、16 个机制 demo'"
Enter
Sleep 500ms

Type "echo '✓ github.com/7hinkDifferent/agent-cracker'"
Enter
Sleep 3s
