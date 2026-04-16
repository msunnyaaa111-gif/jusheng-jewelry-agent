from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.models.session import SessionState
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

    def test_detect_more_options_request_as_rerank(self) -> None:
        state = SessionState(budget=500.0, category=["手链"], gift_target="自戴")

        result = self.parser._heuristic_parse(
            message="有没有其他款式",
            session_state=state,
        )

        self.assertEqual(result["action"], "RERANK_AND_RECOMMEND")
        self.assertFalse(result["needs_followup"])

    def test_detect_more_options_request_with_natural_de_particle(self) -> None:
        state = SessionState(budget=500.0, category=["手链"], gift_target="自戴")

        result = self.parser._heuristic_parse(
            message="还有其他的款式吗？",
            session_state=state,
        )

        self.assertEqual(result["action"], "RERANK_AND_RECOMMEND")
        self.assertFalse(result["needs_followup"])

    def test_detect_more_options_request_with_recommend_more_phrase(self) -> None:
        state = SessionState(budget=500.0, category=["手链"], gift_target="自戴")

        result = self.parser._heuristic_parse(
            message="再推荐几款看看",
            session_state=state,
        )

        self.assertEqual(result["action"], "RERANK_AND_RECOMMEND")
        self.assertFalse(result["needs_followup"])

    def test_detect_more_options_request_with_switch_phrase(self) -> None:
        state = SessionState(budget=500.0, category=["手链"], gift_target="自戴")

        result = self.parser._heuristic_parse(
            message="换几款看看",
            session_state=state,
        )

        self.assertEqual(result["action"], "RERANK_AND_RECOMMEND")
        self.assertFalse(result["needs_followup"])

    def test_detect_more_options_request_with_have_other_phrase(self) -> None:
        state = SessionState(budget=500.0, category=["手链"], gift_target="自戴")

        result = self.parser._heuristic_parse(
            message="还有别的手串吗",
            session_state=state,
        )

        self.assertEqual(result["action"], "RERANK_AND_RECOMMEND")
        self.assertFalse(result["needs_followup"])

    def test_detect_more_options_request_with_short_particle_phrase(self) -> None:
        state = SessionState(
            budget=400.0,
            category=["手链"],
            color_preferences=["紫色"],
            last_recommended_codes=["A001", "A002"],
        )

        result = self.parser._heuristic_parse(
            message="还有其他的嘛？",
            session_state=state,
        )

        self.assertEqual(result["action"], "RERANK_AND_RECOMMEND")
        self.assertFalse(result["needs_followup"])

    def test_detect_stateful_rerank_for_unlisted_short_followup(self) -> None:
        state = SessionState(
            budget=400.0,
            category=["手链"],
            color_preferences=["紫色"],
            last_recommended_codes=["A001", "A002"],
        )

        result = self.parser._heuristic_parse(
            message="那再来点别的吧",
            session_state=state,
        )

        self.assertEqual(result["action"], "RERANK_AND_RECOMMEND")
        self.assertFalse(result["needs_followup"])

    def test_changed_budget_should_refresh_instead_of_rerank(self) -> None:
        state = SessionState(
            budget=400.0,
            category=["手链"],
            color_preferences=["紫色"],
            last_recommended_codes=["A001", "A002"],
        )

        result = self.parser._heuristic_parse(
            message="我现在预算一千五，再给我推荐几款",
            session_state=state,
        )

        self.assertEqual(result["action"], "RETRIEVE_AND_RECOMMEND")
        self.assertTrue(result["should_refresh_retrieval"])

    def test_extract_color_and_budget_from_precise_request(self) -> None:
        conditions = self.parser.extract_explicit_conditions("我想要蓝色的项链，预算500元")

        self.assertEqual(conditions["category"], ["项链"])
        self.assertEqual(conditions["color_preferences"], ["蓝色"])
        self.assertEqual(conditions["budget"], 500.0)

    def test_extract_colloquial_budget_amount(self) -> None:
        conditions = self.parser.extract_explicit_conditions("我现在预算大概在一千五，你再给我推荐几款")

        self.assertEqual(conditions["budget"], 1500.0)

    def test_extract_colloquial_budget_range_and_flexibility(self) -> None:
        conditions = self.parser.extract_explicit_conditions("三四百的项链有吗")

        self.assertEqual(conditions["category"], ["项链"])
        self.assertEqual(conditions["budget"], 350.0)
        self.assertEqual(conditions["budget_flexibility"], 50.0)

    def test_budget_is_required_before_recommendation_even_with_color_and_target(self) -> None:
        state = SessionState(category=["手链"], color_preferences=["蓝色"], gift_target="自戴")

        result = self.parser._heuristic_parse(
            message="送给我自己",
            session_state=state,
        )

        self.assertEqual(result["action"], "ASK_FOLLOWUP")
        self.assertIn("预算", result["followup_question"])


    def test_extract_budget_unrestricted_and_yellow_color(self) -> None:
        conditions = self.parser.extract_explicit_conditions("我想看黄色手串，预算都可以")

        self.assertEqual(conditions["category"], ["手链"])
        self.assertEqual(conditions["color_preferences"], ["榛勮壊"])
        self.assertTrue(conditions["budget_unrestricted"])

    def test_extract_negative_style_and_positive_style(self) -> None:
        conditions = self.parser.extract_explicit_conditions("我不喜欢新中式，喜欢时尚点的")

        self.assertEqual(conditions["excluded_style_preferences"], ["新中式"])
        self.assertEqual(conditions["style_preferences"], ["时尚"])

    def test_extract_negative_material_preference(self) -> None:
        conditions = self.parser.extract_explicit_conditions("我不喜欢和田玉")

        self.assertEqual(conditions["main_material"], [])
        self.assertEqual(conditions["excluded_main_material"], ["和田玉"])

    def test_budget_unrestricted_allows_recommendation_without_numeric_budget(self) -> None:
        state = SessionState(category=["手链"], color_preferences=["黄色"])

        result = self.parser._heuristic_parse(
            message="预算都可以",
            session_state=state,
        )

        self.assertEqual(result["action"], "RETRIEVE_AND_RECOMMEND")
        self.assertFalse(result["needs_followup"])


    def test_extract_feature_preference_and_negative_feature(self) -> None:
        conditions = self.parser.extract_explicit_conditions("我不喜欢大颗粒，想要小颗粒一点")

        self.assertEqual(conditions["excluded_feature_preferences"], ["大颗粒"])
        self.assertEqual(conditions["feature_preferences"], ["小颗粒"])

    def test_feature_adjustment_should_refresh_instead_of_rerank(self) -> None:
        state = SessionState(
            budget=500.0,
            category=["鎵嬮摼"],
            gift_target="鑷埓",
            last_recommended_codes=["A001", "A002"],
        )

        result = self.parser._heuristic_parse(
            message="我不要太成熟的，想年轻一点",
            session_state=state,
        )

        self.assertEqual(result["action"], "RETRIEVE_AND_RECOMMEND")
        self.assertTrue(result["should_refresh_retrieval"])
        self.assertIn("成熟", result["conditions"]["excluded_preferences"])

if __name__ == "__main__":
    unittest.main()
