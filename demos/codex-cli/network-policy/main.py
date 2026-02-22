"""
Codex CLI — 网络策略引擎 Demo

演示 codex-cli 独有的网络安全机制：
- 域名规范化（大小写、端口、方括号处理）
- glob 模式匹配（精确 / 子域 / apex+子域）
- SSRF 防护（私有 IP 检测：loopback/private/link-local/CGNAT）
- 白名单/黑名单策略组合

Run: uv run python main.py
"""

from policy import (
    normalize_host,
    DomainPattern,
    is_non_public_ip,
    is_loopback_host,
    NetworkPolicy,
    NetworkDecision,
)


def decision_icon(d: NetworkDecision) -> str:
    return "ALLOW" if d == NetworkDecision.ALLOW else "DENY "


def print_section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


print("=" * 60)
print("  Codex CLI — 网络策略引擎 Demo")
print("  复现 network-proxy/src/policy.rs 的域名匹配与 SSRF 防护")
print("=" * 60)


# ── Demo 1: 域名规范化 ───────────────────────────────────────────

print_section("Demo 1: 域名规范化")

normalize_cases = [
    ("Example.COM", "大写 → 小写"),
    ("api.github.com.", "去尾点"),
    ("host:8080", "去端口"),
    ("[::1]", "去方括号（IPv6）"),
    ("  API.Example.COM.  ", "综合：空格+大写+尾点"),
]

for host, desc in normalize_cases:
    result = normalize_host(host)
    print(f"  {host:<25s} → {result:<25s}  ({desc})")


# ── Demo 2: 域名模式匹配 ─────────────────────────────────────────

print_section("Demo 2: 域名模式匹配（三种模式）")

patterns = [
    ("github.com", "精确匹配"),
    ("*.github.com", "仅子域"),
    ("**.github.com", "apex + 子域"),
    ("*", "通配所有"),
]

test_hosts = ["github.com", "api.github.com", "raw.api.github.com", "evil.com"]

print(f"\n  {'模式':<22s}", end="")
for h in test_hosts:
    print(f" {h:<22s}", end="")
print()
print(f"  {'─' * 22}", end="")
for _ in test_hosts:
    print(f" {'─' * 22}", end="")
print()

for pattern_str, desc in patterns:
    p = DomainPattern(pattern_str)
    print(f"  {pattern_str:<22s}", end="")
    for h in test_hosts:
        match = "YES" if p.matches(h) else " - "
        print(f" {match:<22s}", end="")
    print(f"  ({desc})")


# ── Demo 3: SSRF 检测 ────────────────────────────────────────────

print_section("Demo 3: SSRF 防护（私有 IP 检测）")

ssrf_cases = [
    # (IP, 预期结果, 类别)
    ("127.0.0.1", True, "Loopback"),
    ("10.0.0.1", True, "Private (10/8)"),
    ("172.16.0.1", True, "Private (172.16/12)"),
    ("192.168.1.1", True, "Private (192.168/16)"),
    ("169.254.1.1", True, "Link-local"),
    ("100.64.0.1", True, "CGNAT (100.64/10)"),
    ("192.0.2.1", True, "TEST-NET-1"),
    ("224.0.0.1", True, "Multicast"),
    ("0.0.0.0", True, "Unspecified"),
    ("::1", True, "IPv6 Loopback"),
    ("8.8.8.8", False, "Public (Google DNS)"),
    ("1.1.1.1", False, "Public (Cloudflare)"),
    ("203.0.114.1", False, "Public (just outside TEST-NET-3)"),
]

for ip, expected, category in ssrf_cases:
    result = is_non_public_ip(ip)
    status = "BLOCKED" if result else "  OK   "
    check = "pass" if result == expected else "FAIL"
    print(f"  [{status}] {ip:<18s} {category:<30s} [{check}]")


# ── Demo 4: 回环主机名检测 ───────────────────────────────────────

print_section("Demo 4: 回环主机名检测")

loopback_cases = [
    "localhost",
    "localhost.localdomain",
    "127.0.0.1",
    "::1",
    "example.com",
    "192.168.1.1",
]

for host in loopback_cases:
    result = is_loopback_host(host)
    status = "LOOPBACK" if result else "NOT    "
    print(f"  [{status}] {host}")


# ── Demo 5: 完整策略评估 ─────────────────────────────────────────

print_section("Demo 5: 完整策略评估（白名单 + 黑名单 + SSRF）")

policy = NetworkPolicy(
    allowlist=[
        "**.github.com",       # GitHub 全域
        "**.npmjs.org",        # npm
        "api.openai.com",      # OpenAI API（精确）
        "*.pypi.org",          # PyPI 子域
    ],
    denylist=[
        "**.evil.com",         # 黑名单域名
        "malware.example.com", # 黑名单特定子域
    ],
    block_ssrf=True,
)

test_requests = [
    # 白名单通过
    "github.com",
    "api.github.com",
    "registry.npmjs.org",
    "api.openai.com",
    "files.pypi.org",
    # 黑名单拒绝
    "evil.com",
    "sub.evil.com",
    "malware.example.com",
    # SSRF 拒绝
    "localhost",
    "127.0.0.1",
    "10.0.0.1",
    "169.254.169.254",         # AWS metadata endpoint
    # 默认拒绝（未在白名单中）
    "unknown-site.com",
    "pypi.org",                # 注意：*.pypi.org 不含 apex
]

print(f"\n  白名单: **.github.com, **.npmjs.org, api.openai.com, *.pypi.org")
print(f"  黑名单: **.evil.com, malware.example.com")
print(f"  SSRF: 启用\n")

for host in test_requests:
    result = policy.evaluate(host)
    icon = decision_icon(result.decision)
    print(f"  [{icon}] {host:<25s} ← {result.source.value}: {result.reason}")

print(f"\n{'=' * 60}")
print("  Demo 完成")
print(f"{'=' * 60}")
