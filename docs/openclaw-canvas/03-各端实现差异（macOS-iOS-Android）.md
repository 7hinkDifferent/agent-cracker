# 03. 各端实现差异（macOS / iOS / Android）

## macOS（最完整）

核心文件：
- `projects/openclaw/apps/macos/Sources/OpenClaw/NodeMode/MacNodeRuntime.swift:83`
- `projects/openclaw/apps/macos/Sources/OpenClaw/CanvasManager.swift:36`
- `projects/openclaw/apps/macos/Sources/OpenClaw/CanvasWindowController.swift:201`

特点：
- `present` 支持 placement（x/y/width/height）。
- panel 可隐藏、复用、按 session 目录持久化。
- 本地内容通过 `openclaw-canvas://` 自定义 scheme 渲染。
- 支持自动监听文件变更并 reload（仅本地 canvas 内容）。
- A2UI 自动导航逻辑最完整（读取 gateway snapshot 的 `canvasHostUrl`）。

## iOS

核心文件：
- `projects/openclaw/apps/ios/Sources/Model/NodeAppModel.swift:925`
- `projects/openclaw/apps/ios/Sources/Model/NodeAppModel+Canvas.swift:10`
- `projects/openclaw/apps/ios/Sources/Screen/ScreenController.swift:28`

特点：
- `present` 忽略 placement（注释明确说明 iOS 全屏）。
- `hide` 实际是回默认 canvas 页面。
- `navigate` 会阻断 loopback host（避免远程网关下误访问本机 127.0.0.1）。
- `snapshot` 默认宽度：png 900 / jpeg 1600（未指定时）。
- A2UI 前会做 ready 轮询，失败报 `A2UI_HOST_UNAVAILABLE`。

## Android

核心文件：
- `projects/openclaw/apps/android/app/src/main/java/ai/openclaw/android/node/InvokeDispatcher.kt:11`
- `projects/openclaw/apps/android/app/src/main/java/ai/openclaw/android/node/CanvasController.kt:20`
- `projects/openclaw/apps/android/app/src/main/java/ai/openclaw/android/node/A2UIHandler.kt:10`

特点：
- `present` 当前等价于 `navigate(url)`。
- `hide` 当前基本 no-op（直接 ok）。
- `canvas/camera/screen` 命令要求前台态，否则报 `NODE_BACKGROUND_UNAVAILABLE`。
- `snapshot` 支持 png/jpeg，质量会钳制。
- A2UI 消息支持 `push` 与 `pushJSONL`，带 v0.8 校验。

## 统一点（跨端都成立）

- 都支持：`present/hide/navigate/eval/snapshot/a2ui.push/pushJSONL/reset`（语义略有差异）。
- 都在 A2UI action bridge 里使用 `openclawCanvasA2UIAction` 通道名。
- 都会把按钮点击等 action 转回 agent 事件（本质“UI 事件 -> Agent 输入”）。

