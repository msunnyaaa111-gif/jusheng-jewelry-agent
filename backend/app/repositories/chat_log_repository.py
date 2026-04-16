from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.config import Settings


class ChatLogRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log_path = self.settings.resolved_user_chat_log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append_log(
        self,
        *,
        session_id: str,
        user_id: str | None,
        request_text: str,
        image_urls: list[str],
        response_mode: str,
        response: dict[str, Any],
        duration_ms: int | None = None,
        status: str = "ok",
        error_message: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "user_id": user_id,
            "request_text": request_text,
            "image_urls": image_urls,
            "response_mode": response_mode,
            "status": status,
            "duration_ms": duration_ms,
            "error_message": error_message,
            "action": response.get("action"),
            "reply_source": response.get("reply_source"),
            "reply_text": response.get("reply_text"),
            "followup_question": response.get("followup_question"),
            "purchase_advice": response.get("purchase_advice"),
            "recommended_product_codes": [
                item.get("product_code")
                for item in (response.get("recommended_products") or [])
                if item.get("product_code")
            ],
            "recommended_product_names": [
                item.get("product_name")
                for item in (response.get("recommended_products") or [])
                if item.get("product_name")
            ],
            "recommended_count": len(response.get("recommended_products") or []),
            "session_state": response.get("session_state") or {},
        }
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def recent_logs(
        self,
        *,
        limit: int = 50,
        session_id: str | None = None,
        user_id: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []

        keyword_normalized = (keyword or "").strip().lower()
        records: list[dict[str, Any]] = []
        for line in reversed(self.log_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if session_id and record.get("session_id") != session_id:
                continue
            if user_id and record.get("user_id") != user_id:
                continue
            if keyword_normalized:
                haystack = " ".join(
                    [
                        str(record.get("request_text") or ""),
                        str(record.get("reply_text") or ""),
                        " ".join(str(item) for item in (record.get("recommended_product_names") or [])),
                        " ".join(str(item) for item in (record.get("recommended_product_codes") or [])),
                    ]
                ).lower()
                if keyword_normalized not in haystack:
                    continue

            records.append(record)
            if len(records) >= limit:
                break
        return records
