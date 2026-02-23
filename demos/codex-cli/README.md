# Codex CLI — Demo Overview

基于 [docs/codex-cli.md](../../docs/codex-cli.md) 分析，以下是构建最小可运行版本和复现特色机制所需的组件。

> Based on commit: [`0a0caa9`](https://github.com/openai/codex/tree/0a0caa9df266ebc124d524ee6ad23ee6513fe501) (2026-02-23)

## MVP 组件

构建最小可运行版本需要以下组件：

- [x] **event-multiplex** — 事件多路复用主循环（tokio select! 多通道并发，消息/工具/中断统一调度）(Python — 原实现 Rust，Python asyncio 等价复现)
- [x] **tool-execution** — Tool 沙箱执行（命令白名单 + sandbox-exec 包装 + 输出捕获）(Python — 原实现 Rust，沙箱策略逻辑可 Python 复现)
- [x] **prompt-assembly** — 多层 Prompt 组装（模板叠加 + 人格注入 + 协作模式 + 策略约束）(Python)
- [x] **response-stream** — 流式响应解析（SSE 流接收 + function call 增量拼接 + 超时处理）(Python)

## 进阶机制

以下是该 agent 的特色功能，可选择性复现：

- [x] **approval-policy** — 三级审批策略（Suggest/Auto-Edit/Full-Auto + ExecPolicy 规则引擎 + 危险命令检测）
- [x] **head-tail-truncation** — 首尾保留截断（bytes/4 token 估算 + UTF-8 边界切割 + 中间截断标记）
- [x] **network-policy** — 网络策略引擎（域名白名单/黑名单 + SSRF 防护 + GlobSet 匹配）
- [x] **sandbox-exec** — 平台沙箱执行（Seatbelt 策略生成 + sandbox-exec 包装 + 读写权限控制）
- [x] **retry-backoff** — 指数退避重试（错误可重试性分类 + 指数退避 + ±10% 抖动）

## 完整串联

- [x] **mini-codex** — 组合以上 MVP 组件的最小完整 agent

## 进度

MVP: 4/4 | 进阶: 5/5 | 串联: 1/1 | 总计: 10/10
