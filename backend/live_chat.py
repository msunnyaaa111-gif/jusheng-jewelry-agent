from __future__ import annotations

import json
import queue
import sys
import threading
import time
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen


HEALTH_URL = "http://127.0.0.1:8000/health"
CHAT_URL = "http://127.0.0.1:8000/api/chat/message"
STREAM_URL = "http://127.0.0.1:8000/api/chat/stream"

HEARTBEAT_MESSAGES = [
    "我正在理解您的需求...",
    "我在整理更贴合您的回复...",
    "我在结合当前条件筛选更合适的结果...",
]


def get_json(url: str) -> dict:
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict, timeout: int = 120) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def stream_sse(url: str, payload: dict, event_queue: queue.Queue) -> None:
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        with urlopen(request, timeout=180) as response:
            current_event = None
            for raw_line in response:
                line = raw_line.decode("utf-8").rstrip("\r\n")
                if not line:
                    current_event = None
                    continue
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                    continue
                if line.startswith("data:"):
                    payload_data = json.loads(line[5:].strip())
                    event_queue.put((current_event or "message", payload_data))
        event_queue.put(("__stream_finished__", None))
    except Exception as exc:  # noqa: BLE001
        event_queue.put(("__stream_error__", repr(exc)))


def run_turn(payload: dict) -> dict:
    event_queue: queue.Queue = queue.Queue()
    worker = threading.Thread(
        target=stream_sse,
        args=(STREAM_URL, payload, event_queue),
        daemon=True,
    )
    worker.start()

    final_response = None
    printed_any_delta = False
    first_delta_received = False
    heartbeat_index = 0
    start_at = time.time()
    last_heartbeat_at = 0.0
    fallback_started = False

    print()
    print("Bot:")

    while True:
        try:
            event, data = event_queue.get(timeout=0.4)
        except queue.Empty:
            elapsed = time.time() - start_at
            if not first_delta_received and elapsed - last_heartbeat_at >= 1.0:
                last_heartbeat_at = elapsed
                message = HEARTBEAT_MESSAGES[min(heartbeat_index, len(HEARTBEAT_MESSAGES) - 1)]
                print(f"[{message}]", flush=True)
                if heartbeat_index < len(HEARTBEAT_MESSAGES) - 1:
                    heartbeat_index += 1

            if not first_delta_received and elapsed >= 6.0 and not fallback_started:
                fallback_started = True
                print("[这轮回复稍慢一些，我先为您切换到更稳的返回方式...]", flush=True)
                final_response = post_json(CHAT_URL, payload, timeout=180)
                print(final_response.get("reply_text", ""), flush=True)
                break
            continue

        if event == "status":
            continue

        if event == "delta":
            text = (data or {}).get("text", "")
            if text:
                if not printed_any_delta:
                    printed_any_delta = True
                first_delta_received = True
                print(text, end="", flush=True)
            continue

        if event == "done":
            final_response = data
            break

        if event == "__stream_error__":
            print("[流式返回不太稳定，我改用完整结果方式继续为您处理...]", flush=True)
            final_response = post_json(CHAT_URL, payload, timeout=180)
            print(final_response.get("reply_text", ""), flush=True)
            break

        if event == "__stream_finished__":
            break

    print()
    return final_response or {}


def main() -> int:
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    try:
        get_json(HEALTH_URL)
    except URLError:
        print("Backend is not running.")
        print("Start it with: .\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
        return 1

    session_id = input("Session ID (press Enter to auto-generate): ").strip()
    if not session_id:
        session_id = "live-" + uuid.uuid4().hex[:8]

    user_id = input("User ID (press Enter for tester): ").strip()
    if not user_id:
        user_id = "tester"

    print()
    print("Live chat started.")
    print(f"session_id: {session_id}")
    print("Type exit to quit.")
    print()

    while True:
        try:
            text = input("You: ").replace("\ufeff", "").replace("\u200b", "").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "text": text,
        }

        final_response = run_turn(payload)

        followup = final_response.get("followup_question")
        if followup:
            print()
            print("Follow-up:")
            print(followup)

        products = final_response.get("recommended_products") or []
        if products:
            print()
            print("Products:")
            for product in products:
                price = product.get("wholesale_price")
                price_text = "TBD" if price is None else str(price)
                print(
                    f"- {product.get('product_name', '')} | "
                    f"{product.get('category', '')} | {price_text}"
                )

        print()

    print("Chat ended.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
