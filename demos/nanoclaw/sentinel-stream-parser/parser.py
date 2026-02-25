"""流式哨兵标记解析器 — NanoClaw Sentinel Stream Parser 核心

基于 src/container-runner.ts 的流式解析逻辑（第 279-333 行）。

NanoClaw 容器通过 stdout 输出结果，但 Claude SDK 也会写日志到 stdout。
哨兵标记 ---NANOCLAW_OUTPUT_START--- / ---NANOCLAW_OUTPUT_END--- 让 host
能从混合流中可靠地提取 JSON 结果。

本模块聚焦 **流式** 场景：数据以任意大小的 chunk 到达，标记可能跨 chunk 边界。
原实现在 container.stdout.on('data', ...) 中逐 chunk 处理，用 parseBuffer
累积未匹配数据，直到完整 START/END 对出现。

关键差异（vs container-spawn demo 的 SentinelParser）:
  - 显式处理标记跨 chunk 边界（buffer 可能包含不完整标记前缀）
  - 记录已解析输出计数和丢弃的日志行数
  - flush() 返回残留 buffer 内容（用于调试）
  - 每次 feed() 返回 ParseEvent 列表（含类型标注）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum


# 哨兵标记（必须与 agent-runner 一致）
OUTPUT_START = "---NANOCLAW_OUTPUT_START---"
OUTPUT_END = "---NANOCLAW_OUTPUT_END---"


class EventType(Enum):
    """解析事件类型"""
    OUTPUT = "output"      # 成功解析出 JSON 输出
    ERROR = "error"        # 标记对内 JSON 解析失败


@dataclass
class ParsedOutput:
    """从哨兵标记对中提取的结构化输出"""
    status: str                        # 'success' | 'error'
    result: str | None = None
    new_session_id: str | None = None
    error: str | None = None


@dataclass
class ParseEvent:
    """单次解析事件"""
    event_type: EventType
    output: ParsedOutput | None = None   # EventType.OUTPUT 时有值
    error_message: str | None = None     # EventType.ERROR 时有值
    raw_json: str | None = None          # 原始 JSON 字符串（调试用）


class StreamingSentinelParser:
    """从逐 chunk 到达的 stdout 流中提取哨兵标记之间的 JSON。

    核心算法（对齐 container-runner.ts 第 302-333 行）:
      1. 每次 feed(chunk) 将 chunk 追加到内部 buffer
      2. 循环搜索 OUTPUT_START 标记
      3. 找到 START 后搜索对应 END 标记
      4. 如果 END 未找到 → break，等待更多数据
      5. 提取 START..END 之间的文本，解析为 JSON
      6. 截断 buffer 到 END 标记之后
      7. 重复直到无完整标记对

    buffer 策略:
      - START 之前的文本是 SDK 日志，可安全丢弃
      - 但可能包含不完整的 START 前缀（如 "---NANOCLAW_O"）
      - 因此只丢弃到最后一个 '-' 之前的内容，保留可能的前缀
    """

    def __init__(self) -> None:
        self._buffer: str = ""
        self._parsed_count: int = 0
        self._error_count: int = 0
        self._discarded_bytes: int = 0

    @property
    def parsed_count(self) -> int:
        """已成功解析的输出数量"""
        return self._parsed_count

    @property
    def error_count(self) -> int:
        """解析失败的标记对数量"""
        return self._error_count

    @property
    def buffer_size(self) -> int:
        """当前 buffer 中的字节数"""
        return len(self._buffer)

    def feed(self, chunk: str) -> list[ParseEvent]:
        """处理一个到达的 chunk，返回新解析出的事件列表。

        对应原实现:
            parseBuffer += chunk;
            while ((startIdx = parseBuffer.indexOf(OUTPUT_START_MARKER)) !== -1) {
                const endIdx = parseBuffer.indexOf(OUTPUT_END_MARKER, startIdx);
                if (endIdx === -1) break;
                ...
                parseBuffer = parseBuffer.slice(endIdx + OUTPUT_END_MARKER.length);
            }
        """
        self._buffer += chunk
        events: list[ParseEvent] = []

        while True:
            start_idx = self._buffer.find(OUTPUT_START)
            if start_idx == -1:
                # 没有 START 标记 — 保留可能的不完整前缀
                # OUTPUT_START 以 "---" 开头，保留末尾可能匹配前缀的部分
                safe_discard = self._find_safe_discard_point()
                if safe_discard > 0:
                    self._discarded_bytes += safe_discard
                    self._buffer = self._buffer[safe_discard:]
                break

            end_idx = self._buffer.find(OUTPUT_END, start_idx + len(OUTPUT_START))
            if end_idx == -1:
                # 有 START 但没有 END — 不完整的标记对，等待更多数据
                # 丢弃 START 之前的日志
                if start_idx > 0:
                    self._discarded_bytes += start_idx
                    self._buffer = self._buffer[start_idx:]
                break

            # 提取 START 和 END 之间的 JSON 文本
            json_str = self._buffer[
                start_idx + len(OUTPUT_START):end_idx
            ].strip()

            # 截断 buffer 到 END 之后
            self._buffer = self._buffer[end_idx + len(OUTPUT_END):]

            # 解析 JSON
            event = self._parse_json(json_str)
            events.append(event)

        return events

    def flush(self) -> str:
        """返回 buffer 中剩余的内容（非 JSON 日志行），并清空 buffer。

        在容器关闭后调用，获取未被哨兵标记包裹的残留文本。
        """
        remaining = self._buffer
        self._buffer = ""
        return remaining

    def _parse_json(self, json_str: str) -> ParseEvent:
        """解析标记对之间的 JSON 字符串"""
        try:
            data = json.loads(json_str)
            output = ParsedOutput(
                status=data.get("status", "error"),
                result=data.get("result"),
                new_session_id=data.get("newSessionId"),
                error=data.get("error"),
            )
            self._parsed_count += 1
            return ParseEvent(
                event_type=EventType.OUTPUT,
                output=output,
                raw_json=json_str,
            )
        except json.JSONDecodeError as e:
            self._error_count += 1
            return ParseEvent(
                event_type=EventType.ERROR,
                error_message=f"JSON parse error: {e}",
                raw_json=json_str,
            )

    def _find_safe_discard_point(self) -> int:
        """找到可以安全丢弃的 buffer 位置。

        OUTPUT_START 以 '---' 开头。如果 buffer 末尾有 '-' 序列，
        它可能是下一个标记的前缀，不能丢弃。
        保守策略：保留最后 len(OUTPUT_START)-1 个字符。
        """
        max_prefix = len(OUTPUT_START) - 1
        if len(self._buffer) <= max_prefix:
            return 0
        return len(self._buffer) - max_prefix
