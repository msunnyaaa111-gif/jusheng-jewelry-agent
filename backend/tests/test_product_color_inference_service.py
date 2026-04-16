from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.services.longcat_client import LongCatClient
from app.services.product_color_inference_service import ProductColorInferenceService


class FakeLongCatClient:
    def __init__(self) -> None:
        self.calls = 0

    async def chat_completion(self, **kwargs) -> str:
        self.calls += 1
        return '{"colors":["蓝色","银色"]}'

    @staticmethod
    def extract_json_block(raw_text: str):
        return LongCatClient.extract_json_block(raw_text)


class ProductColorInferenceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_infers_and_caches_product_colors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "product-color-cache.json"
            settings = Settings(
                longcat_api_key="test-key",
                longcat_model="LongCat-Flash-Chat",
                longcat_vision_model="LongCat-Flash-Omni-2603",
                product_color_cache_path=str(cache_path),
            )
            client = FakeLongCatClient()
            service = ProductColorInferenceService(settings, client)
            product = {
                "product_code": "JS-001",
                "product_name": "测试项链",
                "product_image_url": "data:image/png;base64,abc123",
                "product_qr_url": "",
            }

            first = await service.get_product_colors(product)
            second = await service.get_product_colors(
                {
                    "product_code": "JS-001",
                    "product_name": "测试项链",
                    "product_image_url": "data:image/png;base64,abc123",
                    "product_qr_url": "",
                }
            )

            self.assertEqual(first, ["蓝色", "银色"])
            self.assertEqual(second, ["蓝色", "银色"])
            self.assertEqual(client.calls, 1)
            self.assertTrue(cache_path.exists())


if __name__ == "__main__":
    unittest.main()
