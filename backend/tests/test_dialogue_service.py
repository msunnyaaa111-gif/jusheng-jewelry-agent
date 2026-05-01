from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.models.session import SessionState
from app.services.condition_parser import BROWSE_REFUSAL_FOLLOWUP, ConditionParser
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

    async def search(
        self,
        state,
        limit: int = 3,
        exclude_product_codes=None,
        relax_structured_gift_target: bool = False,
    ):
        self.exclude_calls.append(list(exclude_product_codes or []))
        if exclude_product_codes:
            return self.more_products[:limit]
        return self.initial_products[:limit]

    def has_structured_gift_target(self, state) -> bool:
        return state.gift_target in {"男款", "退休妈妈款"}

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


class FakeExhaustedStructuredTargetRecommendationService(FakeRecommendationService):
    def __init__(self) -> None:
        super().__init__()
        self.relax_calls: list[bool] = []
        self.more_products = [
            self._product("N001", "未标注人群备选款1"),
            self._product("N002", "未标注人群备选款2"),
        ]

    async def search(
        self,
        state,
        limit: int = 3,
        exclude_product_codes=None,
        relax_structured_gift_target: bool = False,
    ):
        self.exclude_calls.append(list(exclude_product_codes or []))
        self.relax_calls.append(relax_structured_gift_target)
        if exclude_product_codes and not relax_structured_gift_target:
            return []
        if exclude_product_codes and relax_structured_gift_target:
            return self.more_products[:limit]
        return self.initial_products[:limit]


class DialogueServiceRerankTests(unittest.IsolatedAsyncioTestCase):
    async def test_self_reply_is_treated_as_affirmative_for_pending_followup(self) -> None:
        service = DialogueService(
            condition_parser=FakeConditionParser(),
            recommendation_service=FakeRecommendationService(),
            longcat_client=SimpleNamespace(settings=SimpleNamespace(llm_enabled=False)),
        )
        self.assertTrue(service._is_affirmative("自己"))

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

    async def test_reject_current_cards_excludes_last_recommendations(self) -> None:
        recommendation_service = FakeRecommendationService()
        longcat_client = SimpleNamespace(settings=SimpleNamespace(llm_enabled=False))
        service = DialogueService(
            condition_parser=ConditionParser(longcat_client=longcat_client),
            recommendation_service=recommendation_service,
            longcat_client=longcat_client,
        )
        session_id = "reject-current-cards-session"
        service.sessions[session_id] = SessionState(
            budget_unrestricted=True,
            last_recommended_codes=["A001", "A002", "A003"],
            seen_recommended_codes=["A001", "A002", "A003"],
            last_retrieval_hash="same-hash",
        )

        result = await service.handle_message(
            session_id=session_id,
            text="\u6709\u5176\u4ed6\u7684\u63a8\u8350\u5417 \u90fd\u53ef\u4ee5 \u4f46\u662f\u6211\u4e0d\u8981\u8fd9\u4e09\u6b3e",
        )

        self.assertEqual(result["action"], "RERANK_AND_RECOMMEND")
        self.assertEqual(
            [item.product_code for item in result["recommended_products"]],
            ["B001", "B002"],
        )
        self.assertEqual(recommendation_service.exclude_calls[0], ["A001", "A002", "A003"])

    async def test_browse_refusal_returns_followup_without_product_cards(self) -> None:
        recommendation_service = FakeRecommendationService()
        longcat_client = SimpleNamespace(settings=SimpleNamespace(llm_enabled=False))
        service = DialogueService(
            condition_parser=ConditionParser(longcat_client=longcat_client),
            recommendation_service=recommendation_service,
            longcat_client=longcat_client,
        )

        result = await service.handle_message(
            session_id="browse-refusal-session",
            text="\u5565\u90fd\u4e0d\u60f3\u770b",
        )

        self.assertEqual(result["action"], "ASK_FOLLOWUP")
        self.assertEqual(result["followup_question"], BROWSE_REFUSAL_FOLLOWUP)
        self.assertEqual(result["recommended_products"], [])
        self.assertEqual(result["session_state"].excluded_preferences, [])
        self.assertEqual(recommendation_service.exclude_calls, [])

        followup = await service.handle_message(
            session_id="browse-refusal-session",
            text="\u63a8\u8350\u4e00\u4e0b\u9879\u94fe",
        )

        self.assertEqual(followup["action"], "ASK_FOLLOWUP")
        self.assertIn("\u9884\u7b97", followup["followup_question"])
        self.assertEqual(followup["recommended_products"], [])
        self.assertEqual(followup["session_state"].excluded_preferences, [])

    async def test_same_budget_after_structured_target_exhaustion_relaxes_people_filter(self) -> None:
        recommendation_service = FakeExhaustedStructuredTargetRecommendationService()
        longcat_client = SimpleNamespace(settings=SimpleNamespace(llm_enabled=False))
        service = DialogueService(
            condition_parser=ConditionParser(longcat_client=longcat_client),
            recommendation_service=recommendation_service,
            longcat_client=longcat_client,
        )
        session_id = "structured-target-exhausted-session"
        service.sessions[session_id] = SessionState(
            budget=400.0,
            category=["手链"],
            gift_target="男款",
            last_recommended_codes=["M001", "M002", "M003"],
            seen_recommended_codes=["M001", "M002", "M003"],
            last_retrieval_hash="same-hash",
        )

        exhausted = await service.handle_message(
            session_id=session_id,
            text="还有其他的吗",
        )
        self.assertEqual(exhausted["action"], "EXPLAIN_NO_RESULT")
        self.assertEqual(
            exhausted["session_state"].pending_followup_type,
            "structured_target_exhausted",
        )

        relaxed = await service.handle_message(
            session_id=session_id,
            text="依旧这个预算",
        )

        self.assertEqual(relaxed["action"], "RERANK_AND_RECOMMEND")
        self.assertEqual([item.product_code for item in relaxed["recommended_products"]], ["N001", "N002"])
        self.assertEqual(recommendation_service.exclude_calls[-1], ["M001", "M002", "M003"])
        self.assertTrue(recommendation_service.relax_calls[-1])

    async def test_condition_change_after_structured_target_exhaustion_does_not_relax_people_filter(self) -> None:
        recommendation_service = FakeExhaustedStructuredTargetRecommendationService()
        longcat_client = SimpleNamespace(settings=SimpleNamespace(llm_enabled=False))
        service = DialogueService(
            condition_parser=ConditionParser(longcat_client=longcat_client),
            recommendation_service=recommendation_service,
            longcat_client=longcat_client,
        )
        session_id = "structured-target-budget-change-session"
        service.sessions[session_id] = SessionState(
            budget=400.0,
            category=["手链"],
            gift_target="男款",
            pending_followup_type="structured_target_exhausted",
            last_recommended_codes=["M001", "M002", "M003"],
            seen_recommended_codes=["M001", "M002", "M003"],
            last_retrieval_hash="same-hash",
        )

        result = await service.handle_message(
            session_id=session_id,
            text="预算改成500元",
        )

        self.assertEqual(result["action"], "RETRIEVE_AND_RECOMMEND")
        self.assertIsNone(result["session_state"].pending_followup_type)
        self.assertFalse(any(recommendation_service.relax_calls))


if __name__ == "__main__":
    unittest.main()
