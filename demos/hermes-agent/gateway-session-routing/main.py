from __future__ import annotations

from gateway_router import GatewayRunner, MessageEvent


def main():
    runner = GatewayRunner(group_sessions_per_user=True)
    events = [
        MessageEvent(platform="telegram", chat_id="dm-100", text="Morning digest?", chat_type="dm", user_id="u-alice"),
        MessageEvent(platform="slack", chat_id="eng", text="Please inspect this incident thread", chat_type="group", user_id="u-bob"),
        MessageEvent(platform="slack", chat_id="eng", thread_id="thread-7", text="Same incident, deeper thread reply", chat_type="group", user_id="u-bob"),
    ]

    print("=" * 72)
    print("Hermes Gateway Session Routing Demo")
    print("=" * 72)

    for event in events:
        key = runner.handle_message(event)
        print(f"[{event.platform}] {event.text}")
        print(f"  -> session_key: {key}")


if __name__ == "__main__":
    main()
