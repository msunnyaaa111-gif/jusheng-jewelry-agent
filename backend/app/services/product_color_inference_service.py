from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.longcat_client import LongCatClient


logger = logging.getLogger(__name__)


COLOR_INFERENCE_SYSTEM_PROMPT = """
You are a jewelry product image color extractor.
Return JSON only with this schema:
{
  "colors": ["蓝色", "白色"]
}

Rules:
- Only use these canonical labels: 蓝色, 绿色, 红色, 粉色, 紫色, 白色, 黑色, 金色, 银色, 黄色, 橙色, 棕色.
- Focus on the jewelry product itself, not the poster background, QR frame, text, or watermark.
- Include at most 3 colors.
- Prefer the dominant visible jewelry color first.
- If the product color cannot be determined reliably, return {"colors": []}.
"""


class ProductColorInferenceService:
    def __init__(self, settings: Settings, longcat_client: LongCatClient) -> None:
        self.settings = settings
        self.longcat_client = longcat_client
        self._cache_lock = asyncio.Lock()
        self._cache_loaded = False
        self._cache: dict[str, dict[str, Any]] = {}

    async def annotate_products(self, products: list[dict[str, Any]]) -> None:
        if not products:
            return
        if not self.settings.llm_enabled:
            return
        vision_model = self.settings.effective_vision_model
        if not LongCatClient.supports_image_inputs(vision_model):
            return

        limit = max(1, self.settings.product_color_inference_limit)
        semaphore = asyncio.Semaphore(max(1, self.settings.product_color_inference_concurrency))

        async def annotate_one(product: dict[str, Any]) -> None:
            async with semaphore:
                colors = await self.get_product_colors(product)
                if colors:
                    product["_inferred_colors"] = colors

        await asyncio.gather(*(annotate_one(product) for product in products[:limit]))

    async def get_product_colors(self, product: dict[str, Any]) -> list[str]:
        existing = self._normalize_colors(product.get("_inferred_colors"))
        if existing:
            return existing

        cache_key = self._build_cache_key(product)
        media_ref = self._preferred_media_ref(product)
        if not cache_key or not media_ref:
            return []

        await self._ensure_cache_loaded()
        cached = self._cache.get(cache_key)
        if cached and cached.get("media_ref") == media_ref:
            colors = self._normalize_colors(cached.get("colors"))
            product["_inferred_colors"] = colors
            return colors

        image_input = self._resolve_image_input(media_ref)
        if not image_input:
            return []

        vision_model = self.settings.effective_vision_model
        if not LongCatClient.supports_image_inputs(vision_model):
            return []

        payload = {
            "product_code": product.get("product_code"),
            "product_name": product.get("product_name"),
            "instruction": "识别珠宝主体颜色，忽略背景与二维码边框。",
        }
        try:
            raw = await self.longcat_client.chat_completion(
                system_prompt=COLOR_INFERENCE_SYSTEM_PROMPT,
                user_payload=payload,
                image_inputs=[image_input],
                temperature=0.01,
                max_tokens=120,
                model=vision_model,
            )
            parsed = self.longcat_client.extract_json_block(raw)
            colors = self._normalize_colors(parsed.get("colors"))
        except Exception:
            logger.exception(
                "Product color inference failed for product_code=%s",
                product.get("product_code"),
            )
            return []

        product["_inferred_colors"] = colors
        await self._write_cache_record(cache_key, media_ref, colors)
        return colors

    async def _ensure_cache_loaded(self) -> None:
        if self._cache_loaded:
            return
        async with self._cache_lock:
            if self._cache_loaded:
                return
            cache_path = self.settings.resolved_product_color_cache_path
            if cache_path.exists():
                try:
                    payload = json.loads(cache_path.read_text(encoding="utf-8"))
                    if isinstance(payload, dict):
                        self._cache = {
                            str(key): value
                            for key, value in payload.items()
                            if isinstance(value, dict)
                        }
                except Exception:
                    logger.exception("Failed to load product color cache from %s", cache_path)
            self._cache_loaded = True

    async def _write_cache_record(
        self,
        cache_key: str,
        media_ref: str,
        colors: list[str],
    ) -> None:
        await self._ensure_cache_loaded()
        async with self._cache_lock:
            self._cache[cache_key] = {
                "media_ref": media_ref,
                "colors": colors,
            }
            cache_path = self.settings.resolved_product_color_cache_path
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _build_cache_key(self, product: dict[str, Any]) -> str:
        product_code = str(product.get("product_code") or "").strip()
        if product_code:
            return product_code
        return str(product.get("product_name") or "").strip()

    def _preferred_media_ref(self, product: dict[str, Any]) -> str | None:
        for value in (
            product.get("product_image_url"),
            product.get("product_qr_url"),
        ):
            text = str(value or "").strip()
            if text:
                return text
        return None

    def _resolve_image_input(self, media_ref: str) -> str | None:
        if media_ref.startswith("data:"):
            return media_ref
        if media_ref.startswith(("http://", "https://")):
            return media_ref
        if not media_ref.startswith("/static/"):
            return None

        relative = media_ref.removeprefix("/static/").replace("/", "\\")
        local_path = self.settings.backend_root / "data" / Path(relative)
        if not local_path.exists():
            return None

        mime_type, _ = mimetypes.guess_type(local_path.name)
        mime_type = mime_type or "application/octet-stream"
        encoded = base64.b64encode(local_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _normalize_colors(self, raw_colors: Any) -> list[str]:
        canonical_map = {
            "蓝": "蓝色",
            "蓝色": "蓝色",
            "海蓝": "蓝色",
            "天蓝": "蓝色",
            "宝蓝": "蓝色",
            "绿": "绿色",
            "绿色": "绿色",
            "翠绿": "绿色",
            "青绿": "绿色",
            "红": "红色",
            "红色": "红色",
            "粉": "粉色",
            "粉色": "粉色",
            "紫": "紫色",
            "紫色": "紫色",
            "白": "白色",
            "白色": "白色",
            "黑": "黑色",
            "黑色": "黑色",
            "金": "金色",
            "金色": "金色",
            "黄": "黄色",
            "黄色": "黄色",
            "银": "银色",
            "银色": "银色",
            "橙": "橙色",
            "橙色": "橙色",
            "棕": "棕色",
            "棕色": "棕色",
        }
        if isinstance(raw_colors, str):
            raw_colors = [raw_colors]
        if not isinstance(raw_colors, list):
            return []

        colors: list[str] = []
        for item in raw_colors:
            text = str(item or "").strip()
            if not text:
                continue
            canonical = canonical_map.get(text, text)
            if canonical not in colors:
                colors.append(canonical)
        return colors[:3]
