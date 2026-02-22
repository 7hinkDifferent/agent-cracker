"""
Codex CLI — 网络策略引擎

复现 codex-rs/network-proxy/src/policy.rs 的核心逻辑：
- 域名规范化（小写、去端口、去方括号、去尾点）
- glob 模式匹配（精确 / *.子域 / **.apex+子域）
- SSRF 防护（私有 IP 检测：loopback/private/link-local/CGNAT）
- 策略决策（Allow / Deny + 来源追踪）
"""

import ipaddress
import re
from enum import Enum
from dataclasses import dataclass
from fnmatch import fnmatch


# ── 枚举定义 ──────────────────────────────────────────────────────

class NetworkDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"


class DecisionSource(Enum):
    """决策来源，用于追踪哪层策略做出了判断。"""
    BASELINE = "baseline"       # 基础策略（全局默认）
    MODE_GUARD = "mode_guard"   # 审批模式约束
    ALLOWLIST = "allowlist"     # 白名单匹配
    DENYLIST = "denylist"       # 黑名单匹配
    SSRF = "ssrf"               # SSRF 检测


@dataclass
class PolicyResult:
    """策略评估结果。"""
    decision: NetworkDecision
    source: DecisionSource
    reason: str
    host: str


# ── 域名规范化 ────────────────────────────────────────────────────

def normalize_host(host: str) -> str:
    """规范化主机名：小写 → 去方括号 → 去端口 → 去尾点。

    与 codex-cli policy.rs 的 normalize_host() 一致：
    - "[::1]" → "::1"
    - "Example.COM." → "example.com"
    - "host:8080" → "host"（仅去除最后一个冒号段，避免误删 IPv6）
    """
    h = host.strip().lower()
    # 去方括号（IPv6 字面量）
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    # 去端口（仅当恰好有一个冒号时，排除 IPv6）
    if h.count(":") == 1:
        h = h.rsplit(":", 1)[0]
    # 去尾点
    h = h.rstrip(".")
    return h


# ── 域名模式匹配 ──────────────────────────────────────────────────

class DomainPattern:
    """域名匹配模式，支持三种形式：

    - "example.com"      → 精确匹配
    - "*.example.com"    → 仅匹配子域（不含 apex）
    - "**.example.com"   → 匹配 apex + 所有子域
    - "*"                → 匹配所有
    """

    def __init__(self, pattern: str):
        self.raw = pattern
        normalized = normalize_host(pattern)

        if normalized == "*":
            self.mode = "any"
            self.domain = ""
        elif normalized.startswith("**."):
            self.mode = "apex_and_subdomains"
            self.domain = normalized[3:]
        elif normalized.startswith("*."):
            self.mode = "subdomains_only"
            self.domain = normalized[2:]
        else:
            self.mode = "exact"
            self.domain = normalized

    def matches(self, host: str) -> bool:
        """检查主机名是否匹配此模式。"""
        h = normalize_host(host)

        if self.mode == "any":
            return True
        elif self.mode == "exact":
            return h == self.domain
        elif self.mode == "subdomains_only":
            # *.example.com → 匹配 sub.example.com，不匹配 example.com
            return h.endswith("." + self.domain) and h != self.domain
        elif self.mode == "apex_and_subdomains":
            # **.example.com → 匹配 example.com 和 sub.example.com
            return h == self.domain or h.endswith("." + self.domain)
        return False

    def __repr__(self) -> str:
        return f"DomainPattern({self.raw!r})"


# ── SSRF 检测 ─────────────────────────────────────────────────────

def is_non_public_ip(ip_str: str) -> bool:
    """检测 IP 是否为非公网地址（私有/保留/回环等）。

    检测范围与 codex-cli policy.rs 的 is_non_public_ip() 一致：
    - Loopback: 127.0.0.0/8, ::1
    - Private: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
    - Link-local: 169.254.0.0/16, fe80::/10
    - CGNAT: 100.64.0.0/10
    - Multicast: 224.0.0.0/4, ff00::/8
    - Reserved: 0.0.0.0/8, 192.0.0.0/24, 192.0.2.0/24, 198.18.0.0/15,
                198.51.100.0/24, 203.0.113.0/24, 240.0.0.0/4
    - IPv6 unique-local: fc00::/7
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    # Python 的 is_private 在 3.11+ 覆盖了大部分情况
    # 但为了教学目的，显式列出所有范围
    if isinstance(ip, ipaddress.IPv4Address):
        return (
            ip.is_loopback          # 127.0.0.0/8
            or ip.is_private        # 10/8, 172.16/12, 192.168/16
            or ip.is_link_local     # 169.254.0.0/16
            or ip.is_multicast      # 224.0.0.0/4
            or ip.is_reserved       # 240.0.0.0/4 等
            or ip.is_unspecified    # 0.0.0.0
            or _in_cidr(ip, "100.64.0.0/10")    # CGNAT
            or _in_cidr(ip, "192.0.0.0/24")     # IETF Protocol Assignments
            or _in_cidr(ip, "192.0.2.0/24")     # TEST-NET-1
            or _in_cidr(ip, "198.18.0.0/15")    # Benchmarking
            or _in_cidr(ip, "198.51.100.0/24")  # TEST-NET-2
            or _in_cidr(ip, "203.0.113.0/24")   # TEST-NET-3
        )
    else:
        return (
            ip.is_loopback          # ::1
            or ip.is_private        # fc00::/7 等
            or ip.is_link_local     # fe80::/10
            or ip.is_multicast      # ff00::/8
            or ip.is_reserved
            or ip.is_unspecified    # ::
        )


def _in_cidr(ip: ipaddress.IPv4Address, cidr: str) -> bool:
    """检查 IPv4 地址是否在 CIDR 范围内。"""
    return ip in ipaddress.ip_network(cidr)


def is_loopback_host(host: str) -> bool:
    """检测主机名是否指向回环地址。"""
    h = normalize_host(host)
    if h in ("localhost", "localhost.localdomain"):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


# ── 网络策略引擎 ──────────────────────────────────────────────────

class NetworkPolicy:
    """网络策略引擎，组合白名单/黑名单/SSRF 检测做出决策。"""

    def __init__(
        self,
        allowlist: list[str] | None = None,
        denylist: list[str] | None = None,
        block_ssrf: bool = True,
    ):
        self.allow_patterns = [DomainPattern(p) for p in (allowlist or [])]
        self.deny_patterns = [DomainPattern(p) for p in (denylist or [])]
        self.block_ssrf = block_ssrf

    def evaluate(self, host: str) -> PolicyResult:
        """评估主机名的网络访问策略。

        决策优先级（与 codex-cli 一致）：
        1. SSRF 检测 → 私有 IP 直接拒绝
        2. 黑名单匹配 → 拒绝
        3. 白名单匹配 → 允许
        4. 默认策略 → 拒绝（安全优先）
        """
        normalized = normalize_host(host)

        # 第一层：SSRF 检测
        if self.block_ssrf:
            if is_loopback_host(normalized):
                return PolicyResult(
                    NetworkDecision.DENY, DecisionSource.SSRF,
                    f"回环地址: {normalized}", host,
                )
            try:
                ip = ipaddress.ip_address(normalized)
                if is_non_public_ip(str(ip)):
                    return PolicyResult(
                        NetworkDecision.DENY, DecisionSource.SSRF,
                        f"非公网 IP: {normalized}", host,
                    )
            except ValueError:
                pass  # 不是 IP，继续域名检查

        # 第二层：黑名单
        for pattern in self.deny_patterns:
            if pattern.matches(normalized):
                return PolicyResult(
                    NetworkDecision.DENY, DecisionSource.DENYLIST,
                    f"匹配黑名单: {pattern.raw}", host,
                )

        # 第三层：白名单
        for pattern in self.allow_patterns:
            if pattern.matches(normalized):
                return PolicyResult(
                    NetworkDecision.ALLOW, DecisionSource.ALLOWLIST,
                    f"匹配白名单: {pattern.raw}", host,
                )

        # 第四层：默认拒绝
        return PolicyResult(
            NetworkDecision.DENY, DecisionSource.BASELINE,
            "默认策略: 未匹配任何白名单", host,
        )
