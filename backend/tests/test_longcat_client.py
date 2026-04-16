from __future__ import annotations

import unittest

from app.core.config import Settings
from app.services.longcat_client import LongCatClient


class LongCatClientPayloadTests(unittest.TestCase):
    def test_build_timeout_uses_split_timeout_settings(self) -> None:
        settings = Settings(
            longcat_api_key="test-key",
            longcat_model="LongCat-Flash-Omni-2603",
            longcat_connect_timeout_seconds=12.0,
            longcat_read_timeout_seconds=88.0,
            longcat_write_timeout_seconds=21.0,
            longcat_pool_timeout_seconds=9.0,
        )
        client = LongCatClient(settings)

        timeout = client._build_timeout()

        self.assertEqual(timeout.connect, 12.0)
        self.assertEqual(timeout.read, 88.0)
        self.assertEqual(timeout.write, 21.0)
        self.assertEqual(timeout.pool, 9.0)

    def test_flash_chat_uses_string_message_format(self) -> None:
        settings = Settings(
            longcat_api_key="test-key",
            longcat_model="LongCat-Flash-Chat",
        )
        client = LongCatClient(settings)

        payload = client._build_request_payload(
            system_prompt="system",
            user_payload={"text": "hello"},
            image_inputs=None,
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
            image_inputs=None,
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

    def test_omni_can_attach_image_inputs(self) -> None:
        settings = Settings(
            longcat_api_key="test-key",
            longcat_model="LongCat-Flash-Omni-2603",
        )
        client = LongCatClient(settings)

        payload = client._build_request_payload(
            system_prompt="system",
            user_payload={"text": "hello"},
            image_inputs=["data:image/png;base64,abc123"],
            temperature=0.4,
            max_tokens=100,
            model=None,
            stream=False,
        )

        self.assertEqual(payload["messages"][1]["content"][1]["type"], "image_url")
        self.assertEqual(
            payload["messages"][1]["content"][1]["image_url"]["url"],
            "data:image/png;base64,abc123",
        )


if __name__ == "__main__":
    unittest.main()
