# OpenClaw — Demo Overview

基于 [docs/openclaw.md](../../docs/openclaw.md) 分析，以下是构建最小可运行版本和复现特色机制所需的组件。

> Based on commit: [`ea47ab2`](https://github.com/openclaw/openclaw/tree/ea47ab29bd6d92394185636a27c3572c19aac8e5) (2026-02-23)

## MVP 组件

构建最小可运行版本需要以下组件：

- [ ] **channel-routing** — Binding 匹配路由引擎，消息→Agent 复合 session key (Python)
- [ ] **gateway-rpc** — WebSocket RPC 服务器，通道标准化接入控制面 (Python)
- [ ] **embedded-engine** — 内嵌 pi-agent 调用链模拟，含 model fallback (Python)
- [ ] **tool-profile** — 4 档渐进 Tool Profile 策略 (minimal→coding→messaging→full) (Python)
- [ ] **system-prompt-builder** — 14+ sections 动态 prompt 组装，含 Skills/Memory/SOUL 注入 (Python)

## 平台机制

以下是超越 coding agent 的平台层机制（D9-D12），可复现为独立 demo：

- [ ] **hybrid-memory** — Vector(70%)+BM25(30%) 混合检索 + MMR 去重 + 时间衰减 (D10: 记忆)
- [ ] **docker-sandbox** — Docker 容器沙箱隔离，含 workspace mount 与 elevated exec (D11: 安全)
- [ ] **cron-scheduler** — 三种调度类型 (at/every/cron) + heartbeat 空闲检测 (D11: 调度)
- [ ] **subagent-orchestration** — spawn+steer+kill 子 Agent 生命周期管理 (D11: 多 Agent)

## 进阶机制

以下是该 agent 的特色功能，可选择性复现：

- [ ] **auth-profile-rotation** — 多 API key 优先级轮转 + cooldown 追踪
- [ ] **channel-dock** — 统一通道能力抽象接口 (capabilities/commands/streaming/threading)
- [ ] **plugin-hook-pipeline** — before_prompt_build→before_agent_start→tool_call→tool_result hook 管道
- [ ] **skills-injection** — 51+ Skills 按需匹配注入 prompt，每轮最多 1 个

## 完整串联

- [ ] **mini-openclaw** — 组合以上 MVP 组件 + 平台机制的最小完整 agent 平台

## 进度

MVP: 0/5 | 平台: 0/4 | 进阶: 0/4 | 串联: 0/1 | 总计: 0/14
