from __future__ import annotations

import unittest

from app.core.config import Settings
from app.services.longcat_client import LongCatClient


class LongCatClientPayloadTests(unittest.TestCase):
    def test_flash_chat_uses_string_message_format(self) -> None:
        settings = Settings(
            longcat_api_key="test-key",
            longcat_model="LongCat-Flash-Chat",
        )
        client = LongCatClient(settings)

        payload = client._build_request_payload(
            system_prompt="system",
            user_payload={"text": "hello"},
            temperature=0.4,
            max_tokens=100,
            model=None,
            stream=False,
        )

        self.assertEqual(payload["model"], "LongCat-Flash-Chat")
        self.assertEqual(payload["messages"][0]["content"], "system")
        self.assertIsInstance(payload["messages"][1]["content"], str)
        self.assertNotIn("output_modalities", payload)

    def test_omni_uses_array_message_format(self) -> None:
        settings = Settings(
            longcat_api_key="test-key",
            longcat_model="LongCat-Flash-Omni-2603",
        )
        client = LongCatClient(settings)

        payload = client._build_request_payload(
            system_prompt="system",
            user_payload={"text": "hello"},
            temperature=0.4,
            max_tokens=100,
            model=None,
            stream=True,
        )

        self.assertEqual(payload["model"], "LongCat-Flash-Omni-2603")
        self.assertEqual(payload["messages"][0]["content"][0]["type"], "text")
        self.assertEqual(payload["messages"][0]["content"][0]["text"], "system")
        self.assertEqual(payload["messages"][1]["content"][0]["type"], "text")
        self.assertEqual(payload["output_modalities"], ["text"])
        self.assertTrue(payload["stream"])


if __name__ == "__main__":
    unittest.main()
