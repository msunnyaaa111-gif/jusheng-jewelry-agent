from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.condition_parser import ConditionParser


class ConditionParserGiftTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        dummy_client = SimpleNamespace(settings=SimpleNamespace(llm_enabled=False))
        self.parser = ConditionParser(longcat_client=dummy_client)

    def test_extract_self_wear_from_send_to_myself_phrase(self) -> None:
        conditions = self.parser.extract_explicit_conditions("我想买项链，预算500元，送给我自己")
        self.assertEqual(conditions["gift_target"], "自戴")

    def test_extract_self_wear_from_buy_for_myself_phrase(self) -> None:
        conditions = self.parser.extract_explicit_conditions("想看一条日常戴的项链，买给我自己")
        self.assertEqual(conditions["gift_target"], "自戴")

    def test_canonicalize_llm_self_target_values(self) -> None:
        self.assertEqual(self.parser._canonicalize_condition("gift_target", "我自己"), "自戴")
        self.assertEqual(self.parser._canonicalize_condition("gift_target", "本人"), "自戴")


if __name__ == "__main__":
    unittest.main()
