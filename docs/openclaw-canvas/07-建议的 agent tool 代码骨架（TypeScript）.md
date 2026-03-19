# 07. 建议的 agent tool 代码骨架（TypeScript）

下面是对齐 OpenClaw 思路的最小骨架（伪代码级，可直接改成项目代码）。

```ts
const CANVAS_ACTIONS = [
  "present",
  "hide",
  "navigate",
  "eval",
  "snapshot",
  "a2ui_push",
  "a2ui_reset",
] as const;

export async function canvasToolExecute(args: Record<string, unknown>) {
  const action = requireString(args, "action");
  const nodeId = await resolveNodeId(args.node);

  const invoke = (command: string, params?: Record<string, unknown>) =>
    gatewayCall("node.invoke", {
      nodeId,
      command,
      params,
      idempotencyKey: crypto.randomUUID(),
    });

  switch (action) {
    case "present": {
      const target = asString(args.target) ?? asString(args.url);
      const placement = {
        x: asNumber(args.x),
        y: asNumber(args.y),
        width: asNumber(args.width),
        height: asNumber(args.height),
      };
      const p: Record<string, unknown> = {};
      if (target) p.url = target;
      if (hasAnyFinite(placement)) p.placement = placement;
      await invoke("canvas.present", p);
      return { ok: true };
    }

    case "hide":
      await invoke("canvas.hide");
      return { ok: true };

    case "navigate": {
      const url = asString(args.url) ?? requireString(args, "target");
      await invoke("canvas.navigate", { url });
      return { ok: true };
    }

    case "eval": {
      const javaScript = requireString(args, "javaScript");
      const raw = await invoke("canvas.eval", { javaScript });
      return raw?.payload?.result ?? "";
    }

    case "snapshot": {
      const format = normalizeFormat(asString(args.outputFormat) ?? "png");
      const raw = await invoke("canvas.snapshot", {
        format,
        maxWidth: asNumber(args.maxWidth),
        quality: asNumber(args.quality),
      });
      const payload = parseSnapshotPayload(raw?.payload); // {format, base64}
      return payload;
    }

    case "a2ui_push": {
      const jsonl = await resolveJsonl(args); // jsonl 或 jsonlPath（二选一）
      await invoke("canvas.a2ui.pushJSONL", { jsonl });
      return { ok: true };
    }

    case "a2ui_reset":
      await invoke("canvas.a2ui.reset");
      return { ok: true };

    default:
      throw new Error(`Unknown action: ${action}`);
  }
}
```

## 建议直接复用的设计点

- `present` 同时兼容 `target/url`。
- `navigate` 兼容 `target` 别名，减少调用方分支。
- `snapshot` 标准返回只认 `{ format, base64 }`。
- `a2ui_push` 保留 `jsonlPath`，但务必做路径白名单校验。

## 若你们要做 Action 回传

页面脚本里暴露：

```js
window.openclawSendUserAction?.({
  id: crypto.randomUUID(),
  name: "hello",
  surfaceId: "main",
  sourceComponentId: "btn.hello",
  context: { ts: Date.now() }
});
```

然后在 native/bridge 侧转成 agent 输入事件即可（可先用文本协议）。

