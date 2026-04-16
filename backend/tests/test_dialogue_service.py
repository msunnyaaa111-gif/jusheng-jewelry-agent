from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.dialogue_service import DialogueService


class FakeConditionParser:
    def extract_explicit_conditions(self, message: str) -> dict:
        if "500" in message:
            return {
                "age": None,
                "budget": 500.0,
                "budget_flexibility": None,
                "category": ["手链"],
                "excluded_categories": [],
                "main_material": [],
                "stone_material": [],
                "color_preferences": [],
                "gift_target": "自戴",
                "usage_scene": None,
                "style_preferences": [],
                "luxury_intent": [],
                "constellation": None,
                "zodiac": None,
                "birthday": None,
                "excluded_preferences": [],
            }
        return {
            "age": None,
            "budget": None,
            "budget_flexibility": None,
            "category": [],
            "excluded_categories": [],
            "main_material": [],
            "stone_material": [],
            "color_preferences": [],
            "gift_target": None,
            "usage_scene": None,
            "style_preferences": [],
            "luxury_intent": [],
            "constellation": None,
            "zodiac": None,
            "birthday": None,
            "excluded_preferences": [],
        }

    async def parse(self, *, message: str, session_state, recent_history):
        if "其他" in message:
            return {
                "action": "RERANK_AND_RECOMMEND",
                "conditions": {},
                "condition_changes": [],
                "should_refresh_retrieval": False,
                "followup_question": None,
                "notes_for_backend": [],
            }
        return {
            "action": "RETRIEVE_AND_RECOMMEND",
            "conditions": self.extract_explicit_conditions(message),
            "condition_changes": [],
            "should_refresh_retrieval": True,
            "followup_question": None,
            "notes_for_backend": [],
        }


class FakeRecommendationService:
    def __init__(self) -> None:
        self.exclude_calls: list[list[str]] = []
        self.initial_products = [
            self._product("A001", "初始款1"),
            self._product("A002", "初始款2"),
            self._product("A003", "初始款3"),
        ]
        self.more_products = [
            self._product("B001", "新款1"),
            self._product("B002", "新款2"),
        ]

    def build_retrieval_hash(self, state) -> str:
        return "same-hash"

    async def search(self, state, limit: int = 3, exclude_product_codes=None):
        self.exclude_calls.append(list(exclude_product_codes or []))
        if exclude_product_codes:
            return self.more_products[:limit]
        return self.initial_products[:limit]

    @staticmethod
    def _product(code: str, name: str) -> dict:
        return {
            "product_code": code,
            "product_name": name,
            "system_category": "手链",
            "group_price": 520.0,
            "wholesale_price": 500.0,
            "discount": 0.75,
            "main_material": "和田玉",
            "stone_material": "",
            "selling_points": "日常佩戴",
            "system_attributes": "通勤日常",
            "suitable_people": "",
            "luxury_flag": "",
            "product_qr_url": "/static/demo.png",
            "product_image_url": "/static/demo.png",
        }


class DialogueServiceRerankTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_message_defaults_to_cards_for_recommendations(self) -> None:
        recommendation_service = FakeRecommendationService()
        service = DialogueService(
            condition_parser=FakeConditionParser(),
            recommendation_service=recommendation_service,
            longcat_client=SimpleNamespace(settings=SimpleNamespace(llm_enabled=False)),
        )

        result = await service.handle_message(
            session_id="cards-default-session",
            text="500 bracelet self",
        )

        self.assertEqual(result["reply_text"], "")
        self.assertEqual(result["reply_source"], "cards")
        self.assertEqual(
            [item.product_code for item in result["recommended_products"]],
            ["A001", "A002", "A003"],
        )

    async def test_rerank_excludes_already_seen_products(self) -> None:
        recommendation_service = FakeRecommendationService()
        service = DialogueService(
            condition_parser=FakeConditionParser(),
            recommendation_service=recommendation_service,
            longcat_client=SimpleNamespace(settings=SimpleNamespace(llm_enabled=False)),
        )

        first = await service.handle_message(
            session_id="rerank-session",
            text="我想买500元的手串 自己戴",
        )
        second = await service.handle_message(
            session_id="rerank-session",
            text="还有其他的款式吗？",
        )

        self.assertEqual(first["action"], "RETRIEVE_AND_RECOMMEND")
        self.assertEqual(
            [item.product_code for item in first["recommended_products"]],
            ["A001", "A002", "A003"],
        )
        self.assertEqual(second["action"], "RERANK_AND_RECOMMEND")
        self.assertEqual(
            [item.product_code for item in second["recommended_products"]],
            ["B001", "B002"],
        )
        self.assertEqual(recommendation_service.exclude_calls[1], ["A001", "A002", "A003"])


if __name__ == "__main__":
    unittest.main()
