from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.models.session import SessionState
from app.services.recommendation_service import RecommendationService


class FakeProductRepository:
    def __init__(self, products: list[dict]) -> None:
        self.products = products

    def load_catalog(self) -> None:
        return None


class FakeColorInferenceService:
    def __init__(self, inferred_colors_by_code: dict[str, list[str]]) -> None:
        self.inferred_colors_by_code = inferred_colors_by_code
        self.annotated_calls = 0

    async def annotate_products(self, products: list[dict]) -> None:
        self.annotated_calls += 1
        for product in products:
            colors = self.inferred_colors_by_code.get(product.get("product_code"), [])
            if colors:
                product["_inferred_colors"] = colors


class RecommendationServiceStrictMatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = SimpleNamespace(
            default_budget_tolerance=0.2,
            product_color_inference_limit=24,
            product_color_inference_concurrency=4,
        )

    async def test_keeps_single_exact_match_without_padding_other_categories(self) -> None:
        repository = FakeProductRepository(
            [
                {
                    "product_code": "N-001",
                    "product_name": "蓝月项链",
                    "system_category": "项链",
                    "wholesale_price": 480.0,
                    "group_price": 599.0,
                    "product_image_url": "https://example.com/n-001.jpg",
                    "suitable_people": "",
                    "main_material": "银",
                    "stone_material": "蓝晶",
                    "system_attributes": "简约",
                    "selling_points": "日常通勤",
                    "luxury_flag": "",
                },
                {
                    "product_code": "B-001",
                    "product_name": "同价位手链",
                    "system_category": "手链",
                    "wholesale_price": 500.0,
                    "group_price": 620.0,
                    "product_image_url": "https://example.com/b-001.jpg",
                    "suitable_people": "",
                    "main_material": "银",
                    "stone_material": "",
                    "system_attributes": "简约",
                    "selling_points": "通勤",
                    "luxury_flag": "",
                },
                {
                    "product_code": "N-002",
                    "product_name": "超预算项链",
                    "system_category": "项链",
                    "wholesale_price": 880.0,
                    "group_price": 999.0,
                    "product_image_url": "https://example.com/n-002.jpg",
                    "suitable_people": "",
                    "main_material": "银",
                    "stone_material": "",
                    "system_attributes": "简约",
                    "selling_points": "通勤",
                    "luxury_flag": "",
                },
            ]
        )
        service = RecommendationService(self.settings, repository)

        results = await service.search(SessionState(budget=500.0, category=["项链"]), limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["product_code"], "N-001")
        self.assertEqual(results[0]["_strict_match_count"], 1)

    async def test_returns_no_results_when_color_condition_has_no_exact_match(self) -> None:
        repository = FakeProductRepository(
            [
                {
                    "product_code": "N-010",
                    "product_name": "暖金项链",
                    "system_category": "项链",
                    "wholesale_price": 520.0,
                    "group_price": 699.0,
                    "product_image_url": "https://example.com/n-010.jpg",
                    "suitable_people": "",
                    "main_material": "金色铜镀层",
                    "stone_material": "",
                    "system_attributes": "轻奢",
                    "selling_points": "香槟金",
                    "luxury_flag": "",
                },
                {
                    "product_code": "N-011",
                    "product_name": "红宝项链",
                    "system_category": "项链",
                    "wholesale_price": 480.0,
                    "group_price": 620.0,
                    "product_image_url": "https://example.com/n-011.jpg",
                    "suitable_people": "",
                    "main_material": "银",
                    "stone_material": "红宝石",
                    "system_attributes": "精致",
                    "selling_points": "酒红配色",
                    "luxury_flag": "",
                },
            ]
        )
        service = RecommendationService(self.settings, repository)

        results = await service.search(
            SessionState(budget=500.0, category=["项链"], color_preferences=["蓝色"]),
            limit=3,
        )

        self.assertEqual(results, [])

    async def test_uses_inferred_image_colors_when_text_fields_have_no_color(self) -> None:
        repository = FakeProductRepository(
            [
                {
                    "product_code": "N-100",
                    "product_name": "简约项链",
                    "system_category": "项链",
                    "wholesale_price": 510.0,
                    "group_price": 699.0,
                    "product_image_url": "https://example.com/n-100.jpg",
                    "suitable_people": "",
                    "main_material": "925银",
                    "stone_material": "",
                    "system_attributes": "通勤",
                    "selling_points": "极简",
                    "luxury_flag": "",
                }
            ]
        )
        color_inference_service = FakeColorInferenceService({"N-100": ["蓝色"]})
        service = RecommendationService(
            self.settings,
            repository,
            color_inference_service=color_inference_service,
        )

        results = await service.search(
            SessionState(budget=500.0, category=["项链"], color_preferences=["蓝色"]),
            limit=3,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["product_code"], "N-100")
        self.assertEqual(results[0]["_strict_match_count"], 1)
        self.assertEqual(color_inference_service.annotated_calls, 1)

    async def test_secondary_inferred_color_does_not_count_as_primary_match(self) -> None:
        repository = FakeProductRepository(
            [
                {
                    "product_code": "N-200",
                    "product_name": "白玉手串",
                    "system_category": "手链",
                    "wholesale_price": 500.0,
                    "group_price": 660.0,
                    "product_image_url": "https://example.com/n-200.jpg",
                    "suitable_people": "",
                    "main_material": "和田玉",
                    "stone_material": "",
                    "system_attributes": "温润",
                    "selling_points": "日常佩戴",
                    "luxury_flag": "",
                }
            ]
        )
        color_inference_service = FakeColorInferenceService({"N-200": ["白色", "蓝色"]})
        service = RecommendationService(
            self.settings,
            repository,
            color_inference_service=color_inference_service,
        )

        results = await service.search(
            SessionState(budget=500.0, category=["手链"], color_preferences=["蓝色"]),
            limit=3,
        )

        self.assertEqual(results, [])


    async def test_prefers_primary_inferred_yellow_over_textual_yellow_accent(self) -> None:
        repository = FakeProductRepository(
            [
                {
                    "product_code": "Y-100",
                    "product_name": "点缀黄珠手串",
                    "system_category": "手链",
                    "wholesale_price": 420.0,
                    "group_price": 520.0,
                    "product_image_url": "https://example.com/y-100.jpg",
                    "suitable_people": "",
                    "main_material": "和田玉",
                    "stone_material": "",
                    "system_attributes": "简约",
                    "selling_points": "少量黄色点缀",
                    "luxury_flag": "",
                },
                {
                    "product_code": "Y-200",
                    "product_name": "主黄手串",
                    "system_category": "手链",
                    "wholesale_price": 430.0,
                    "group_price": 540.0,
                    "product_image_url": "https://example.com/y-200.jpg",
                    "suitable_people": "",
                    "main_material": "琥珀",
                    "stone_material": "",
                    "system_attributes": "时尚",
                    "selling_points": "亮黄色主色",
                    "luxury_flag": "",
                },
            ]
        )
        color_inference_service = FakeColorInferenceService(
            {
                "Y-100": ["白色", "黄色"],
                "Y-200": ["黄色"],
            }
        )
        service = RecommendationService(self.settings, repository, color_inference_service=color_inference_service)

        results = await service.search(
            SessionState(budget=400.0, category=["手链"], color_preferences=["黄色"]),
            limit=3,
        )

        self.assertEqual([item["product_code"] for item in results], ["Y-200"])

    async def test_excluded_material_filters_out_hetianyu_even_with_zodiac_preference(self) -> None:
        repository = FakeProductRepository(
            [
                {
                    "product_code": "M-100",
                    "product_name": "和田玉手串",
                    "system_category": "手链",
                    "wholesale_price": 300.0,
                    "group_price": 399.0,
                    "product_image_url": "https://example.com/m-100.jpg",
                    "suitable_people": "",
                    "main_material": "和田玉",
                    "stone_material": "",
                    "system_attributes": "温润",
                    "selling_points": "日常佩戴",
                    "luxury_flag": "",
                },
                {
                    "product_code": "M-200",
                    "product_name": "水晶手串",
                    "system_category": "手链",
                    "wholesale_price": 310.0,
                    "group_price": 420.0,
                    "product_image_url": "https://example.com/m-200.jpg",
                    "suitable_people": "",
                    "main_material": "水晶",
                    "stone_material": "",
                    "system_attributes": "时尚",
                    "selling_points": "星座礼物",
                    "luxury_flag": "",
                },
            ]
        )
        service = RecommendationService(self.settings, repository)

        results = await service.search(
            SessionState(
                budget=300.0,
                category=["手链"],
                zodiac="狗",
                excluded_main_material=["和田玉"],
            ),
            limit=3,
        )

        self.assertEqual([item["product_code"] for item in results], ["M-200"])

    async def test_excluded_material_filters_out_real_chinese_hetianyu(self) -> None:
        repository = FakeProductRepository(
            [
                {
                    "product_code": "RC-100",
                    "product_name": "\u548c\u7530\u7389\u624b\u4e32",
                    "system_category": "\u624b\u94fe",
                    "wholesale_price": 300.0,
                    "group_price": 399.0,
                    "product_image_url": "https://example.com/rc-100.jpg",
                    "suitable_people": "",
                    "main_material": "\u548c\u7530\u7389",
                    "stone_material": "",
                    "system_attributes": "\u6e29\u6da6",
                    "selling_points": "\u65e5\u5e38\u4f69\u6234",
                    "luxury_flag": "",
                },
                {
                    "product_code": "RC-200",
                    "product_name": "\u6c34\u6676\u624b\u4e32",
                    "system_category": "\u624b\u94fe",
                    "wholesale_price": 310.0,
                    "group_price": 420.0,
                    "product_image_url": "https://example.com/rc-200.jpg",
                    "suitable_people": "",
                    "main_material": "\u6c34\u6676",
                    "stone_material": "",
                    "system_attributes": "\u65f6\u5c1a",
                    "selling_points": "\u661f\u5ea7\u793c\u7269",
                    "luxury_flag": "",
                },
            ]
        )
        service = RecommendationService(self.settings, repository)

        results = await service.search(
            SessionState(
                budget=300.0,
                category=["\u624b\u94fe"],
                excluded_main_material=["\u548c\u7530\u7389"],
            ),
            limit=3,
        )

        self.assertEqual([item["product_code"] for item in results], ["RC-200"])

    async def test_positive_style_prefilter_and_negative_style_exclusion(self) -> None:
        repository = FakeProductRepository(
            [
                {
                    "product_code": "S-100",
                    "product_name": "新中式手串",
                    "system_category": "手链",
                    "wholesale_price": 450.0,
                    "group_price": 560.0,
                    "product_image_url": "https://example.com/s-100.jpg",
                    "suitable_people": "",
                    "main_material": "玛瑙",
                    "stone_material": "",
                    "system_attributes": "新中式 国风",
                    "selling_points": "东方韵味",
                    "luxury_flag": "",
                },
                {
                    "product_code": "S-200",
                    "product_name": "时尚手串",
                    "system_category": "手链",
                    "wholesale_price": 460.0,
                    "group_price": 580.0,
                    "product_image_url": "https://example.com/s-200.jpg",
                    "suitable_people": "",
                    "main_material": "水晶",
                    "stone_material": "",
                    "system_attributes": "时尚 简约",
                    "selling_points": "日常百搭",
                    "luxury_flag": "",
                },
            ]
        )
        service = RecommendationService(self.settings, repository)

        results = await service.search(
            SessionState(
                budget=450.0,
                category=["手链"],
                style_preferences=["时尚"],
                excluded_style_preferences=["新中式"],
            ),
            limit=3,
        )

        self.assertEqual([item["product_code"] for item in results], ["S-200"])

    async def test_feature_preference_prefilter_and_negative_feature_exclusion(self) -> None:
        repository = FakeProductRepository(
            [
                {
                    "product_code": "F-100",
                    "product_name": "圆珠手串",
                    "system_category": "鎵嬮摼",
                    "wholesale_price": 430.0,
                    "group_price": 520.0,
                    "product_image_url": "https://example.com/f-100.jpg",
                    "suitable_people": "",
                    "main_material": "姘存櫠",
                    "stone_material": "",
                    "system_attributes": "成熟低调 圆珠",
                    "selling_points": "大颗粒存在感",
                    "luxury_flag": "",
                },
                {
                    "product_code": "F-200",
                    "product_name": "小颗粒桶珠手串",
                    "system_category": "鎵嬮摼",
                    "wholesale_price": 440.0,
                    "group_price": 540.0,
                    "product_image_url": "https://example.com/f-200.jpg",
                    "suitable_people": "",
                    "main_material": "姘存櫠",
                    "stone_material": "",
                    "system_attributes": "年轻轻盈 桶珠",
                    "selling_points": "小颗粒更日常",
                    "luxury_flag": "",
                },
            ]
        )
        service = RecommendationService(self.settings, repository)

        results = await service.search(
            SessionState(
                budget=430.0,
                category=["鎵嬮摼"],
                feature_preferences=["小颗粒"],
                excluded_feature_preferences=["圆珠", "成熟"],
            ),
            limit=3,
        )

        self.assertEqual([item["product_code"] for item in results], ["F-200"])


if __name__ == "__main__":
    unittest.main()
