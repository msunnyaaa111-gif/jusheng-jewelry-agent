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


if __name__ == "__main__":
    unittest.main()
