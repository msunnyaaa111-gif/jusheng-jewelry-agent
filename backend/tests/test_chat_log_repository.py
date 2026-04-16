from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.repositories.chat_log_repository import ChatLogRepository


class ChatLogRepositoryTests(unittest.TestCase):
    def test_append_and_filter_recent_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = SimpleNamespace(
                resolved_user_chat_log_path=Path(temp_dir) / "user_chat_logs.jsonl",
            )
            repository = ChatLogRepository(settings)

            repository.append_log(
                session_id="session-a",
                user_id="user-1",
                request_text="我想看蓝色手串",
                image_urls=[],
                response_mode="cards",
                response={
                    "action": "RETRIEVE_AND_RECOMMEND",
                    "reply_source": "cards",
                    "reply_text": "",
                    "followup_question": None,
                    "purchase_advice": "先看蓝色系",
                    "recommended_products": [
                        {"product_code": "A001", "product_name": "蓝色手串"},
                    ],
                    "session_state": {"category": ["手链"]},
                },
                duration_ms=120,
            )
            repository.append_log(
                session_id="session-b",
                user_id="user-2",
                request_text="不要和田玉，想年轻一点",
                image_urls=[],
                response_mode="cards",
                response={
                    "action": "RETRIEVE_AND_RECOMMEND",
                    "reply_source": "cards",
                    "reply_text": "",
                    "followup_question": None,
                    "purchase_advice": None,
                    "recommended_products": [
                        {"product_code": "B001", "product_name": "年轻感水晶手串"},
                    ],
                    "session_state": {"excluded_main_material": ["和田玉"]},
                },
                duration_ms=180,
            )

            filtered_by_session = repository.recent_logs(session_id="session-a")
            self.assertEqual(len(filtered_by_session), 1)
            self.assertEqual(filtered_by_session[0]["user_id"], "user-1")

            filtered_by_keyword = repository.recent_logs(keyword="和田玉")
            self.assertEqual(len(filtered_by_keyword), 1)
            self.assertEqual(filtered_by_keyword[0]["session_id"], "session-b")

            recent = repository.recent_logs(limit=2)
            self.assertEqual([item["session_id"] for item in recent], ["session-b", "session-a"])


if __name__ == "__main__":
    unittest.main()
