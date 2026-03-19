# OpenClaw Canvas 调研包（agent-cracker）

更新时间：2026-03-05（本地源码静态调研，无外网依赖）

## 你会在这里看到什么

- `01-架构总览与调用链.md`：从 agent tool 到 WebView 渲染的全链路。
- `02-动作协议与参数细节.md`：`present/hide/navigate/eval/snapshot/a2ui_push/a2ui_reset` 的协议与行为。
- `03-各端实现差异（macOS-iOS-Android）.md`：三端节点实现差异和踩坑点。
- `04-安全模型与权限边界.md`：capability、认证、路径限制、命令白名单。
- `05-最小实现难度评估与落地步骤.md`：最小可用版本的难度评估、分阶段步骤、工时估计。
- `06-demo方案（优先复用 OpenClaw Canvas）.md`：可直接执行的 demo 方案。
- `07-建议的 agent tool 代码骨架（TypeScript）.md`：可以直接开工的 tool 结构草图。

## 一页结论

- 这套能力本质是：`Canvas Tool(Agent)` -> `Gateway node.invoke` -> `Node Runtime` -> `WebView/Panel`。
- OpenClaw 已经把协议、渲染、A2UI v0.8、Action 回传、安全能力 token 都打通了。
- 对我们来说，最小实现难度是 **中等偏低**（如果复用 OpenClaw 渲染）；若完全自建渲染容器则是 **中等偏高**。
- 推荐路线：
  1. 先复刻 tool 协议层（1-2 天）。
  2. 先跑通 `present/navigate/eval/snapshot`（1 天）。
  3. 再加 `a2ui_push/a2ui_reset` + Action 回传（1-2 天）。

