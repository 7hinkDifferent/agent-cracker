# VHS tape file for recording demo GIF
# Install: brew install vhs
# Run: vhs demo.tape
# Output: demo.gif

Output demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 900
Set Height 500
Set Theme "Dracula"
Set Padding 20

# Title
Type "# Agent Cracker — 拆解 Coding Agent 的核心机制"
Enter
Sleep 1s

Type "# 演示: aider 的 SEARCH/REPLACE 解析器 (100 行复现)"
Enter
Sleep 1s

# Run the demo
Type "cd demos/aider/search-replace && uv run python main.py"
Enter
Sleep 5s

# Show the result
Type ""
Enter
Sleep 2s

Type "# 再看 prompt 组装机制"
Enter
Sleep 500ms

Type "cd ../prompt-assembly && uv run python main.py"
Enter
Sleep 5s

Type ""
Enter
Sleep 2s

Type "# 所有 demo 都是 100-200 行的最小复现 ✓"
Enter
Sleep 2s
