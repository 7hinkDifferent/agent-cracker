# Demo: NanoClaw — Channel 抽象层

## 目标

用最简代码复现 NanoClaw 的 Channel 接口抽象与 JID 路由机制。

## 原理

NanoClaw 支持多个消息平台（WhatsApp、Telegram、Discord 等）作为用户交互通道。为了让 Host Orchestrator 不关心底层平台差异，所有通道实现统一的 Channel 接口。每个通道通过 `owns_jid()` 方法声明自己负责哪些 JID（会话标识符），路由器遍历通道列表找到匹配者完成消息投递。

这种设计使得添加新平台只需实现一个 Channel 类，无需修改核心调度逻辑。

```
              收到消息 (JID = "120363xxxx@g.us")
                   |
                   v
            +──────────────+
            | find_channel |  遍历 channels[]
            +──────┬───────+
                   |
          +────────┴────────+
          v                 v
   +─────────────+   +─────────────+
   |  WhatsApp   |   |  Telegram   |
   | owns_jid()  |   | owns_jid()  |
   | @g.us  Y    |   | tg:  N      |
   | @s.whats Y  |   |             |
   +──────┬──────+   +─────────────+
          |
          v  匹配!
   send_message(jid, text)
```

## 运行

```bash
cd demos/nanoclaw/channel-abstraction
uv run python main.py
```

无外部依赖，仅使用 Python 标准库。

## 文件结构

```
demos/nanoclaw/channel-abstraction/
├── README.md       # 本文件
├── channel.py      # Channel Protocol + WhatsApp/Telegram 实现 + 路由
└── main.py         # 4 个演示场景
```

## 关键代码解读

### Channel Protocol（channel.py）

使用 Python 的 `typing.Protocol` 对应 TypeScript 的 `interface Channel`：

```python
@runtime_checkable
class Channel(Protocol):
    name: str
    def connect(self) -> None: ...
    def send_message(self, jid: str, text: str) -> None: ...
    def is_connected(self) -> bool: ...
    def owns_jid(self, jid: str) -> bool: ...
    def disconnect(self) -> None: ...
```

`@runtime_checkable` 使得可以用 `isinstance(wa, Channel)` 在运行时验证实现是否符合接口。

### JID 路由（channel.py）

路由逻辑极其简单——遍历并匹配：

```python
def find_channel(channels, jid):
    for ch in channels:
        if ch.owns_jid(jid):
            return ch
    return None
```

每个通道自己定义 JID 匹配规则：
- **WhatsApp**: `jid.endswith("@g.us")` 或 `jid.endswith("@s.whatsapp.net")`
- **Telegram**: `jid.startswith("tg:")`

### 出站路由（channel.py）

`route_outbound()` 在 `find_channel()` 基础上增加连接状态检查：

```python
def route_outbound(channels, jid, text):
    ch = find_channel(channels, jid)
    if ch is None:
        raise ValueError(f"No channel for JID: {jid}")
    if not ch.is_connected():
        raise RuntimeError(f"Channel '{ch.name}' is not connected")
    ch.send_message(jid, text)
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 接口定义 | TypeScript interface（编译期检查） | Python Protocol + @runtime_checkable（运行时检查） |
| 异步模型 | async/await (Promise) | 同步（简化演示） |
| WhatsApp 连接 | Baileys 库 + QR 认证 + 重连逻辑 | Mock 实现（connect 只设标志位） |
| Telegram | 通过 skill 安装 | 内建 Mock 实现 |
| 消息投递 | WebSocket 长连接 | 列表记录（sent_messages） |
| 输入打字状态 | setTyping?() 可选方法 | 未实现（非核心） |
| 错误恢复 | 出站队列 + 重试 | 直接抛异常 |
| 群组元数据 | onChatMetadata 回调 + 定期同步 | 未实现 |

## 相关文档

- 分析文档: [docs/nanoclaw.md](../../../docs/nanoclaw.md)（D9: 通道层）
- 原项目: https://github.com/qwibitai/nanoclaw
- 核心源码: `src/types.ts`（Channel interface）、`src/channels/whatsapp.ts`、`src/router.ts`
- Based on commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
