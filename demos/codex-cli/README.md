# Codex CLI — Demo Overview

基于 [docs/codex-cli.md](../../docs/codex-cli.md) 分析，以下是值得复现的核心机制。

## Demo 清单

- [ ] **approval-policy** — 三级审批策略（Suggest/Auto-Edit/Full-Auto + ExecPolicy 规则引擎 + 危险命令检测）
- [ ] **sandbox-exec** — 平台沙箱执行（Seatbelt 策略生成 + sandbox-exec 包装 + 读写权限控制）
- [ ] **head-tail-truncation** — 首尾保留截断（bytes/4 token 估算 + UTF-8 边界切割 + 中间截断标记）
- [ ] **retry-backoff** — 指数退避重试（错误可重试性分类 + 指数退避 + ±10% 抖动）
- [ ] **network-policy** — 网络策略引擎（域名白名单/黑名单 + SSRF 防护 + GlobSet 匹配）
- [ ] **prompt-assembly** — 多层 Prompt 组装（模板叠加 + 人格注入 + 协作模式 + 策略约束）

## 进度

0/6 已完成
