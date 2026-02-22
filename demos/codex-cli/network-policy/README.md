# Demo: Codex CLI — 网络策略引擎（Network Policy）

## 目标

用最简代码复现 Codex CLI 独有的网络安全机制：域名策略匹配 + SSRF 防护。

## 原理

Codex CLI 通过独立的 `network-proxy` crate 实现网络访问控制。每个出站请求都经过策略引擎评估，决定是否放行。这是同类 Coding Agent 中唯一实现了完整网络策略的设计。

核心机制：
1. **域名规范化**：统一大小写、去除端口/方括号/尾点，确保匹配一致性
2. **三种模式匹配**：
   - `example.com` — 精确匹配
   - `*.example.com` — 仅匹配子域（不含 apex）
   - `**.example.com` — 匹配 apex + 所有子域
3. **SSRF 防护**：检测私有 IP（loopback、private、link-local、CGNAT、TEST-NET 等），阻止 Agent 访问内网
4. **多层决策**：SSRF 检测 → 黑名单 → 白名单 → 默认拒绝

## 运行

```bash
cd demos/codex-cli/network-policy
uv run python main.py
```

## 文件结构

```
demos/codex-cli/network-policy/
├── README.md      # 本文件
├── policy.py      # 网络策略引擎（域名匹配 + SSRF 检测 + 策略评估）
└── main.py        # 演示：域名匹配、SSRF 检测、策略评估
```

## 关键代码解读

### 域名模式匹配

```python
class DomainPattern:
    # "*.example.com"  → 仅子域（sub.example.com YES, example.com NO）
    # "**.example.com" → apex + 子域（两者都 YES）
    # "example.com"    → 精确匹配
    # "*"              → 通配所有
```

### SSRF 检测

```python
def is_non_public_ip(ip_str):
    # 检测所有 RFC 定义的非公网地址：
    # - 127.0.0.0/8 (loopback)
    # - 10/8, 172.16/12, 192.168/16 (private)
    # - 169.254.0.0/16 (link-local)
    # - 100.64.0.0/10 (CGNAT)
    # - 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 (TEST-NET)
```

### 决策优先级

```
SSRF 检测（最高优先级）→ 黑名单 → 白名单 → 默认拒绝
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 语言 | Rust（policy.rs） | Python |
| 模式匹配 | GlobSet（编译优化） | fnmatch + 手动匹配 |
| 协议 | HTTP/HTTPS/SOCKS5/UDP | 仅域名层面 |
| Unix Socket | 可配置控制 | 无 |
| 代理 | 完整 HTTP/SOCKS5 代理实现 | 无，仅策略引擎 |
| IP 解析 | DNS 异步解析 + 缓存 | 仅检测直接 IP 输入 |

## 相关文档

- 分析文档: [docs/codex-cli.md](../../../docs/codex-cli.md)
- 原项目: https://github.com/openai/codex
- 核心源码: `codex-rs/network-proxy/src/policy.rs`
