"""消息游标推进与失败回滚 — NanoClaw 双游标系统核心

基于 src/index.ts (lastTimestamp + lastAgentTimestamp) 和
src/db.ts (getRouterState / setRouterState / getNewMessages / getMessagesSince)。

核心机制:
  1. 全局游标 (global_cursor): 消息轮询的已读水位，读取后立即推进
  2. 组群游标 (group_cursors[group]): 每组 agent 处理水位，仅成功后推进
  3. 失败回滚: agent 失败时组群游标不推进（或回滚到 previous），下次轮询重新投递
  4. 部分输出保护: 若已发送输出给用户，不回滚（防止重复发送）
  5. 状态持久化: 游标状态可序列化存储，进程重启后恢复

这实现了 at-least-once delivery 语义:
  - 消息至少被处理一次（失败时重新投递）
  - 但可能被处理多次（agent 失败后重试）
  - 部分输出保护防止用户看到重复消息
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    """模拟消息，对应 src/db.ts 中的 NewMessage。"""
    id: str
    group: str          # chat_jid
    sender: str
    content: str
    timestamp: str      # ISO 8601，用于游标比较


class CursorManager:
    """双游标管理器，复现 src/index.ts 中的 lastTimestamp + lastAgentTimestamp。

    原实现中:
    - lastTimestamp: 模块级变量，startMessageLoop 中 getNewMessages 返回后立即更新
    - lastAgentTimestamp: Record<string, string>，processGroupMessages 中成功后更新
    - 两者通过 saveState() 持久化到 SQLite router_state 表

    游标比较语义: timestamp > cursor（严格大于），与 SQL WHERE timestamp > ? 一致。
    """

    def __init__(self) -> None:
        # 全局游标: 消息轮询已读水位
        self.global_cursor: str = ""
        # 每组游标: agent 处理已确认水位
        self.group_cursors: dict[str, str] = {}

    # ----- 全局游标操作 -----

    def advance_global(self, new_ts: str) -> None:
        """推进全局游标。对应 startMessageLoop 中:
            lastTimestamp = newTimestamp;
            saveState();

        在消息被读取后立即调用，不等待 agent 处理完成。
        这确保同一批消息不会在下一个 poll 周期被重复读取。
        """
        if new_ts > self.global_cursor:
            self.global_cursor = new_ts

    # ----- 组群游标操作 -----

    def advance_group(self, group: str, new_ts: str) -> None:
        """推进组群游标（仅在 agent 成功处理后调用）。

        对应 processGroupMessages 中 agent 成功路径:
            lastAgentTimestamp[chatJid] = missedMessages[missedMessages.length - 1].timestamp;
            saveState();

        以及 startMessageLoop 中的管道成功路径:
            lastAgentTimestamp[chatJid] = messagesToSend[messagesToSend.length - 1].timestamp;
            saveState();
        """
        current = self.group_cursors.get(group, "")
        if new_ts > current:
            self.group_cursors[group] = new_ts

    def get_group_cursor(self, group: str) -> str:
        """获取组群当前游标位置。"""
        return self.group_cursors.get(group, "")

    def rollback_group(self, group: str, previous_cursor: str) -> None:
        """回滚组群游标到之前的位置。

        对应 processGroupMessages 中的错误处理路径:
            // Roll back cursor so retries can re-process these messages
            lastAgentTimestamp[chatJid] = previousCursor;
            saveState();

        注意: 在原实现中，游标是先乐观推进再回滚的:
            const previousCursor = lastAgentTimestamp[chatJid] || '';
            lastAgentTimestamp[chatJid] = missedMessages[...].timestamp;
            saveState();
            // ... agent 执行 ...
            if (error && !outputSentToUser) {
                lastAgentTimestamp[chatJid] = previousCursor;
                saveState();
            }
        """
        self.group_cursors[group] = previous_cursor

    # ----- 消息过滤 -----

    def get_pending_messages(self, group: str, messages: list[Message]) -> list[Message]:
        """获取组群游标之后的待处理消息。

        对应 src/db.ts:getMessagesSince:
            SELECT ... FROM messages WHERE chat_jid = ? AND timestamp > ?

        以及 processGroupMessages 中:
            const sinceTimestamp = lastAgentTimestamp[chatJid] || '';
            const missedMessages = getMessagesSince(chatJid, sinceTimestamp, ...);
        """
        cursor = self.group_cursors.get(group, "")
        return [m for m in messages if m.group == group and m.timestamp > cursor]

    def get_new_messages(self, messages: list[Message]) -> list[Message]:
        """获取全局游标之后的新消息（跨所有组群）。

        对应 src/db.ts:getNewMessages:
            SELECT ... FROM messages WHERE timestamp > ? AND chat_jid IN (...)
        """
        return [m for m in messages if m.timestamp > self.global_cursor]

    # ----- 状态持久化 -----

    def save_state(self) -> dict:
        """序列化游标状态。对应 saveState():
            setRouterState('last_timestamp', lastTimestamp);
            setRouterState('last_agent_timestamp', JSON.stringify(lastAgentTimestamp));
        """
        return {
            "last_timestamp": self.global_cursor,
            "last_agent_timestamp": dict(self.group_cursors),
        }

    def load_state(self, data: dict) -> None:
        """从持久化数据恢复游标状态。对应 loadState():
            lastTimestamp = getRouterState('last_timestamp') || '';
            lastAgentTimestamp = agentTs ? JSON.parse(agentTs) : {};
        """
        self.global_cursor = data.get("last_timestamp", "")
        self.group_cursors = dict(data.get("last_agent_timestamp", {}))

    # ----- 调试输出 -----

    def dump(self, label: str = "") -> None:
        """打印当前游标状态（调试用）。"""
        prefix = f"[{label}] " if label else ""
        print(f"  {prefix}全局游标: {self.global_cursor or '(empty)'}")
        if self.group_cursors:
            for g, ts in sorted(self.group_cursors.items()):
                print(f"  {prefix}  组群 {g}: {ts}")
        else:
            print(f"  {prefix}  (无组群游标)")
