"""
Pi-Agent Structured Compaction Demo

演示 pi-agent 的结构化上下文压缩：
  1. 构建一段长对话（模拟 Agent 编码过程）
  2. 触发首次压缩 → 展示结构化摘要（Goal/Progress/Decisions/...）
  3. 继续对话 → 触发第二次压缩 → 展示增量 UPDATE 合并

原实现: packages/coding-agent/src/core/compaction/compaction.ts
运行: uv run --with litellm python main.py
  （无 API key 时使用 mock 摘要演示流程）
"""

import os
from compaction import (
    estimate_tokens, total_tokens, find_cut_point,
    should_compact, compact,
)


def build_coding_conversation() -> list[dict]:
    """构建一段模拟的 Agent 编码对话"""
    return [
        {"role": "user", "content": "帮我重构 src/auth.py，把登录逻辑从单体函数拆成 AuthService 类，支持 OAuth 和密码登录两种方式。"},
        {"role": "assistant", "content": "好的，让我先阅读当前的 auth.py 文件。\n\n[tool: read src/auth.py]\n\n文件有 320 行，核心是一个 `login()` 函数，包含了密码验证、OAuth 回调处理、session 创建等所有逻辑。我的重构计划：\n\n1. 创建 `AuthService` 基类\n2. 实现 `PasswordAuth` 和 `OAuthAuth` 两个子类\n3. 保持原有的 API 接口不变"},
        {"role": "user", "content": "好的，开始吧。先创建基类。"},
        {"role": "assistant", "content": "[tool: edit src/auth.py]\n\n已创建 `AuthService` 抽象基类，定义了 `authenticate(credentials)` 和 `create_session(user)` 两个抽象方法。同时添加了 `validate_token(token)` 作为共享方法。"},
        {"role": "user", "content": "基类看起来不错。继续实现 PasswordAuth。"},
        {"role": "assistant", "content": "[tool: edit src/auth.py]\n\n已实现 `PasswordAuth(AuthService)`:\n- `authenticate()`: bcrypt 密码验证\n- `create_session()`: JWT token 生成\n- 保留了原有的密码强度检查逻辑\n\n[tool: bash python -m pytest tests/test_auth.py]\n\n运行测试：8/10 通过，2 个失败（OAuth 相关，还没实现）。"},
        {"role": "user", "content": "好。现在实现 OAuthAuth。注意要支持 Google 和 GitHub 两个 provider。"},
        {"role": "assistant", "content": "[tool: edit src/auth.py]\n[tool: edit src/oauth_config.py]\n\n已实现 `OAuthAuth(AuthService)`:\n- 支持 Google 和 GitHub provider\n- OAuth 回调处理抽象为 `handle_callback(provider, code)`\n- 自动创建或关联已有用户\n\n[tool: bash python -m pytest tests/test_auth.py -v]\n\n全部 10 个测试通过！\n\n重构完成，代码从 1 个 320 行函数变为 3 个类（共 280 行），每个类职责清晰。"},
        {"role": "user", "content": "很好。现在帮我更新 API 路由，使用新的 AuthService。"},
        {"role": "assistant", "content": "[tool: read src/routes/auth_routes.py]\n\n当前路由直接调用 `login()` 函数。需要改为注入 AuthService。\n\n[tool: edit src/routes/auth_routes.py]\n\n已更新路由：\n- `/api/auth/login` → `PasswordAuth.authenticate()`\n- `/api/auth/oauth/<provider>` → `OAuthAuth.authenticate()`\n- `/api/auth/callback` → `OAuthAuth.handle_callback()`\n- 添加了依赖注入：`get_auth_service(provider)`"},
        {"role": "user", "content": "路由更新好了。帮我写集成测试。"},
        {"role": "assistant", "content": "[tool: write tests/test_auth_integration.py]\n\n已创建集成测试文件，包含 6 个测试：\n1. 密码登录成功\n2. 密码登录失败（错误密码）\n3. OAuth Google 登录流程\n4. OAuth GitHub 登录流程\n5. Token 验证\n6. Session 过期处理\n\n[tool: bash python -m pytest tests/ -v]\n\n16/16 测试全部通过！"},
    ]


def build_more_conversation() -> list[dict]:
    """续建对话（用于触发第二次压缩）"""
    return [
        {"role": "user", "content": "现在帮我添加日志记录，记录所有认证尝试。"},
        {"role": "assistant", "content": "[tool: edit src/auth.py]\n\n已在 AuthService 基类添加 `_log_attempt()` 方法，记录：\n- 时间戳、IP 地址、认证方式\n- 成功/失败状态\n- 失败时的错误类型\n\n使用 Python logging 模块，输出到 auth.log。"},
        {"role": "user", "content": "好。再加一个限流功能，同一 IP 5 分钟内最多 10 次尝试。"},
        {"role": "assistant", "content": "[tool: edit src/auth.py]\n[tool: write src/rate_limiter.py]\n\n已实现限流：\n- `RateLimiter` 类使用滑动窗口算法\n- 默认 5 分钟窗口，10 次上限\n- 超限返回 429 Too Many Requests\n- 在 AuthService.authenticate() 中自动检查\n\n[tool: bash python -m pytest tests/ -v]\n\n20/20 测试全部通过！"},
        {"role": "user", "content": "最后，帮我更新 README 的认证部分文档。"},
        {"role": "assistant", "content": "[tool: read README.md]\n[tool: edit README.md]\n\n已更新 README 的 Authentication 章节：\n- 新增 AuthService 架构说明\n- 添加 OAuth 配置指南\n- 添加限流说明\n- 更新 API 端点列表"},
    ]


def main():
    print("=" * 60)
    print("Pi-Agent Structured Compaction Demo")
    print("结构化摘要 + 增量 UPDATE 的上下文压缩")
    print("=" * 60)

    has_llm = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    model = os.environ.get("DEMO_MODEL", "openai/gpt-4o-mini")
    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("DEMO_MODEL", "anthropic/claude-haiku-4-5-20251001")

    if not has_llm:
        print("\n⚠  无 API key，使用 mock 摘要演示流程。")
        print("  设置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY 可使用真实 LLM。")

    # ── Step 1：构建初始对话 ──────────────────────────────────

    print("\n── Step 1：构建对话 ──\n")
    messages = build_coding_conversation()
    tokens = total_tokens(messages)
    print(f"  消息数: {len(messages)}")
    print(f"  估算 token: {tokens}")
    print(f"  各消息 token 分布:")
    for i, msg in enumerate(messages):
        t = estimate_tokens(msg)
        role = msg["role"]
        preview = msg["content"][:40].replace("\n", " ") + "..."
        print(f"    [{i:2d}] {role:>9} | {t:4d} tok | {preview}")

    # ── Step 2：演示切割点查找 ────────────────────────────────

    print("\n── Step 2：切割点查找 ──\n")
    # 用较小的 keep_recent 值演示切割效果
    keep_recent = 300
    cut_index = find_cut_point(messages, keep_recent)
    print(f"  keep_recent_tokens = {keep_recent}")
    print(f"  切割点: index {cut_index}")
    print(f"  压缩部分: messages[0:{cut_index}] ({cut_index} 条)")
    print(f"  保留部分: messages[{cut_index}:] ({len(messages) - cut_index} 条)")

    # 展示切割位置
    for i, msg in enumerate(messages):
        marker = "  ✂️" if i == cut_index else "   "
        side = "压缩 ←" if i < cut_index else "保留 →"
        preview = msg["content"][:35].replace("\n", " ") + "..."
        print(f"  {marker} [{i:2d}] {msg['role']:>9} | {side} | {preview}")

    # ── Step 3：首次压缩 ──────────────────────────────────────

    print("\n── Step 3：首次压缩（初始摘要）──\n")
    result = compact(
        messages,
        keep_recent_tokens=keep_recent,
        model=model if has_llm else None,
    )

    print(f"  压缩了 {result['discarded_count']} 条消息")
    print(f"  Token: {result['tokens_before']} → {result['tokens_after']}")
    print(f"  压缩率: {result['tokens_after'] / max(result['tokens_before'], 1):.1%}")
    print(f"\n  ── 结构化摘要 ──")
    for line in result["summary"].split("\n"):
        print(f"  │ {line}")

    # ── Step 4：继续对话 + 第二次压缩（增量 UPDATE）──────────

    print("\n── Step 4：增量 UPDATE 压缩 ──\n")
    # 添加更多对话
    more = build_more_conversation()
    all_messages = result["kept_messages"] + more
    print(f"  添加 {len(more)} 条新消息")
    print(f"  当前总 token: {total_tokens(all_messages)}")

    result2 = compact(
        all_messages,
        keep_recent_tokens=keep_recent,
        previous_summary=result["summary"],  # 传入上次摘要 → UPDATE 模式
        model=model if has_llm else None,
    )

    print(f"  压缩了 {result2['discarded_count']} 条消息")
    print(f"  Token: {result2['tokens_before']} → {result2['tokens_after']}")
    print(f"\n  ── 更新后的摘要（增量 UPDATE）──")
    for line in result2["summary"].split("\n"):
        print(f"  │ {line}")

    # ── Step 5：阈值触发判断 ──────────────────────────────────

    print("\n── Step 5：阈值触发判断 ──\n")
    test_cases = [
        (500, 100, "小窗口，需要压缩"),
        (128000, 16384, "大窗口，不需要"),
    ]
    for window, reserve, desc in test_cases:
        need = should_compact(messages, context_window=window, reserve_tokens=reserve)
        print(f"  context_window={window:>6}, reserve={reserve:>5} → "
              f"{'需要压缩' if need else '无需压缩'} ({desc})")

    # ── 总结 ──────────────────────────────────────────────────

    print(f"\n{'=' * 60}")
    print("核心要点:")
    print("  1. Token 估算: chars/4（简单启发式，保守高估）")
    print("  2. 切割点: 从末尾向前累积，在 user/assistant 边界切")
    print("  3. 结构化摘要: Goal/Progress/Decisions/Next Steps/Context")
    print("  4. 增量 UPDATE: 第二次压缩更新已有摘要，不从头写")
    print("  5. 阈值触发: contextTokens > contextWindow - reserveTokens")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
