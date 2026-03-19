# 06. demo 方案（优先复用 OpenClaw Canvas）

## 方案目标

在最短时间内验证两件事：
- 我们自己的 agent tool 能控制 canvas（present/navigate/eval/snapshot）
- A2UI 能推送与回传 action

## Demo 架构

```text
our agent tool
  -> gateway node.invoke
  -> OpenClaw node runtime
  -> OpenClaw Canvas/WebView
```

不先自建渲染容器，直接复用 OpenClaw Canvas。

## 最小演示脚本（参考）

> 命令基于 OpenClaw CLI；你们可按自有入口映射。

1) 打开 canvas

```bash
openclaw nodes canvas present --node <node-id>
```

2) 导航到本地默认页面

```bash
openclaw nodes canvas navigate --node <node-id> "/"
```

3) 执行 JS 验证

```bash
openclaw nodes canvas eval --node <node-id> --js "document.title"
```

4) 截图验证

```bash
openclaw nodes canvas snapshot --node <node-id> --format jpg
```

5) 推 A2UI 文本（最快 smoke）

```bash
openclaw nodes canvas a2ui push --node <node-id> --text "Hello from A2UI"
```

## A2UI JSONL 示例（v0.8）

```json
{"surfaceUpdate":{"surfaceId":"main","components":[{"id":"root","component":{"Column":{"children":{"explicitList":["title","content"]}}}},{"id":"title","component":{"Text":{"text":{"literalString":"Canvas Demo"},"usageHint":"h1"}}},{"id":"content","component":{"Text":{"text":{"literalString":"A2UI v0.8 push works."},"usageHint":"body"}}}]}}
{"beginRendering":{"surfaceId":"main","root":"root"}}
```

## 验收 checklist

- [ ] `present` 后可见 canvas
- [ ] `navigate` 到目标地址成功
- [ ] `eval` 返回结果稳定
- [ ] `snapshot` 能拿到 base64/图片
- [ ] `a2ui_push` 正常渲染
- [ ] action 点击可回传到 agent（若本阶段已接）

