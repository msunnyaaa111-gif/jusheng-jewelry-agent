from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.config import Settings
from app.models.session import SessionState
from app.repositories.product_repository import ProductRepository
from app.services.product_color_inference_service import ProductColorInferenceService

PREMIUM_HINT_KEYWORDS = [
    "K金",
    "18K",
    "黄金",
    "锆石",
    "钻",
    "镶",
    "珐琅",
    "玫瑰金",
    "厚金",
    "厚磨砂金",
]

MATERIAL_SYNONYMS = {
    "奇楠": ["奇楠", "棋楠"],
    "棋楠": ["棋楠", "奇楠"],
    "沉香": ["沉香", "沉香木", "野生沉香"],
    "沉香木": ["沉香木", "沉香", "野生沉香"],
    "野生沉香": ["野生沉香", "沉香", "沉香木"],
    "降真香": ["降真香", "棋楠", "奇楠"],
    "老山檀": ["老山檀", "檀香", "棋楠", "奇楠"],
}


MATERIAL_SYNONYMS.update(
    {
        "\u548c\u7530\u7389": [
            "\u548c\u7530\u7389",
            "\u548c\u7530\u767d\u7389",
            "\u767d\u7389",
            "18k\u548c\u7530\u7389",
            "18K\u548c\u7530\u7389",
        ],
        "\u6c34\u6676": [
            "\u6c34\u6676",
            "\u767d\u6c34\u6676",
            "\u7d2b\u6c34\u6676",
            "\u9ec4\u6c34\u6676",
            "\u8336\u6676",
            "\u53d1\u6676",
            "\u8d85\u4e03",
            "\u8349\u8393\u6676",
        ],
        "\u73cd\u73e0": ["\u73cd\u73e0", "\u6de1\u6c34\u73cd\u73e0"],
        "\u9ec4\u91d1": ["\u9ec4\u91d1", "\u8db3\u91d1", "\u91d1\u5b50", "\u91d1\u9970"],
        "K\u91d1": ["K\u91d1", "18K", "18k", "18K\u91d1", "18k\u91d1"],
        "\u94f6": ["\u94f6", "925\u94f6", "S925", "s925", "\u7eaf\u94f6"],
        "\u739b\u7459": ["\u739b\u7459", "\u5357\u7ea2"],
        "\u7425\u73c0": ["\u7425\u73c0", "\u871c\u8721"],
        "\u7fe1\u7fe0": ["\u7fe1\u7fe0"],
    }
)

CONSTELLATION_RULES = {
    "白羊座": {"main_material": ["K金"], "style_preferences": ["大气"]},
    "金牛座": {"main_material": ["黄金", "和田玉"], "style_preferences": ["高级感"]},
    "双子座": {"stone_material": ["锆石"], "style_preferences": ["精致"]},
    "巨蟹座": {"main_material": ["珍珠"], "style_preferences": ["温柔"]},
    "狮子座": {"main_material": ["黄金"], "style_preferences": ["显贵"]},
    "处女座": {"main_material": ["K金"], "style_preferences": ["简约"]},
    "天秤座": {"stone_material": ["锆石"], "style_preferences": ["精致"]},
    "天蝎座": {"main_material": ["K金"], "style_preferences": ["轻奢", "高级感"]},
    "射手座": {"main_material": ["红宝石"], "style_preferences": ["大气"]},
    "摩羯座": {"main_material": ["和田玉"], "style_preferences": ["高级感"]},
    "水瓶座": {"stone_material": ["锆石"], "style_preferences": ["简约"]},
    "双鱼座": {"main_material": ["珍珠"], "style_preferences": ["温柔"]},
}

ZODIAC_RULES = {
    "鼠": {"main_material": ["K金"], "style_preferences": ["精致"]},
    "牛": {"main_material": ["和田玉"], "style_preferences": ["高级感"]},
    "虎": {"main_material": ["黄金"], "style_preferences": ["大气"]},
    "兔": {"main_material": ["珍珠"], "style_preferences": ["温柔"]},
    "龙": {"main_material": ["黄金"], "style_preferences": ["显贵"]},
    "蛇": {"main_material": ["K金"], "style_preferences": ["轻奢"]},
    "马": {"main_material": ["红宝石"], "style_preferences": ["大气"]},
    "羊": {"main_material": ["珍珠"], "style_preferences": ["温柔"]},
    "猴": {"stone_material": ["锆石"], "style_preferences": ["精致"]},
    "鸡": {"main_material": ["K金"], "style_preferences": ["轻奢"]},
    "狗": {"main_material": ["和田玉"], "style_preferences": ["通勤"]},
    "猪": {"main_material": ["珍珠"], "style_preferences": ["温柔"]},
}


SCORE_CATEGORY_MATCH = 48
SCORE_GIFT_TARGET_MATCH = 38
SCORE_LUXURY_MATCH = 35
SCORE_MATERIAL_MATCH = 42
SCORE_STYLE_MATCH = 20
SCORE_DEFAULT_WEIGHT = 8
SCORE_DISCOUNT_WEIGHT = 8
SCORE_IMAGE_FEATURE_MATCH = 16
SCORE_COLOR_MATCH = 24
SCORE_SYMBOL_PREFERENCE_MATCH = 10
SCORE_SYMBOL_STYLE_MATCH = 6
SCORE_SYMBOL_STONE_MATCH = 6
SCORE_PREMIUM_UPGRADE = 20


class RecommendationService:
    def __init__(
        self,
        settings: Settings,
        product_repository: ProductRepository,
        color_inference_service: ProductColorInferenceService | None = None,
    ) -> None:
        self.settings = settings
        self.product_repository = product_repository
        self.color_inference_service = color_inference_service

    def build_retrieval_hash(self, state: SessionState) -> str:
        payload = {
            "age": state.age,
            "budget": state.budget,
            "budget_unrestricted": state.budget_unrestricted,
            "category": state.category,
            "excluded_categories": state.excluded_categories,
            "main_material": state.main_material,
            "stone_material": state.stone_material,
            "excluded_main_material": state.excluded_main_material,
            "excluded_stone_material": state.excluded_stone_material,
            "color_preferences": state.color_preferences,
            "feature_preferences": state.feature_preferences,
            "excluded_feature_preferences": state.excluded_feature_preferences,
            "gift_target": state.gift_target,
            "style_preferences": state.style_preferences,
            "excluded_style_preferences": state.excluded_style_preferences,
            "luxury_intent": state.luxury_intent,
            "constellation": state.constellation,
            "zodiac": state.zodiac,
            "excluded_preferences": state.excluded_preferences,
            "image_features": state.image_features,
            "premium_upgrade_intent": state.premium_upgrade_intent,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    async def search(
        self,
        state: SessionState,
        limit: int = 3,
        exclude_product_codes: list[str] | None = None,
        relax_structured_gift_target: bool = False,
    ) -> list[dict[str, Any]]:
        self.product_repository.load_catalog()
        products = self.product_repository.products
        symbol_preferences = self._collect_symbol_preferences(state)
        priority_profile = self._build_priority_profile(state)
        excluded_codes = {code for code in (exclude_product_codes or []) if code}

        candidates = self._filter_products(
            products=products,
            state=state,
            tolerance=self.settings.default_budget_tolerance,
        )
        if excluded_codes:
            candidates = [
                product
                for product in candidates
                if product.get("product_code") not in excluded_codes
            ]

        candidates = await self._apply_priority_prefilters(
            candidates,
            state,
            relax_structured_gift_target=relax_structured_gift_target,
        )
        if not candidates:
            return []

        scored = []
        for product in candidates:
            score = self._score_product(product, state, priority_profile, symbol_preferences)
            distance = self._budget_distance(product, state.budget)
            scored.append((score, distance, product))

        scored.sort(key=lambda item: item[0], reverse=True)

        results = []
        strict_match_count = min(len(scored), limit)
        for _, _, product in scored[:limit]:
            enriched = dict(product)
            enriched["_strict_match_count"] = strict_match_count
            results.append(enriched)
        return results

    def _build_priority_profile(self, state: SessionState) -> dict[str, int]:
        has_category = bool(state.category)
        has_gift_target = bool(state.gift_target)
        has_material = bool(state.main_material or state.stone_material)
        has_luxury = bool(state.luxury_intent or state.style_preferences)

        return {
            "category": SCORE_CATEGORY_MATCH if has_category else SCORE_DEFAULT_WEIGHT + 2,
            "gift_target": SCORE_GIFT_TARGET_MATCH if has_gift_target else SCORE_DEFAULT_WEIGHT,
            "luxury": SCORE_LUXURY_MATCH if has_luxury else SCORE_DEFAULT_WEIGHT,
            "style": SCORE_STYLE_MATCH if has_luxury else SCORE_DEFAULT_WEIGHT + 2,
            "material": SCORE_MATERIAL_MATCH if has_material else SCORE_DEFAULT_WEIGHT,
            "discount": SCORE_DISCOUNT_WEIGHT,
        }

    async def _apply_priority_prefilters(
        self,
        candidates: list[dict[str, Any]],
        state: SessionState,
        *,
        relax_structured_gift_target: bool = False,
    ) -> list[dict[str, Any]]:
        filtered = list(candidates)

        if self._is_plain_self_wear(state):
            neutral_people = [
                product
                for product in filtered
                if not self._has_structured_audience(product)
            ]
            if neutral_people:
                filtered = neutral_people

        structured_target = self._structured_gift_target(state)
        if structured_target:
            by_people = [
                product
                for product in filtered
                if structured_target in (product.get("suitable_people") or "")
            ]
            if relax_structured_gift_target:
                prioritized_codes = {product.get("product_code") for product in by_people}
                remaining = [
                    product
                    for product in filtered
                    if product.get("product_code") not in prioritized_codes
                ]
                filtered = by_people + remaining
            else:
                filtered = by_people

        if self._has_material_priority(state):
            by_material = [
                product
                for product in filtered
                if self._matches_requested_material(product, state)
            ]
            if by_material:
                filtered = by_material

        if state.color_preferences:
            if self.color_inference_service is not None:
                await self.color_inference_service.annotate_products(filtered)
            filtered = [
                product
                for product in filtered
                if self._matches_primary_color_preferences(product, state.color_preferences)
            ]

        if state.style_preferences:
            by_style = [
                product
                for product in filtered
                if self._matches_style_preferences(product, state.style_preferences)
            ]
            if by_style:
                filtered = by_style

        if state.feature_preferences:
            by_feature = [
                product
                for product in filtered
                if self._matches_feature_preferences(product, state.feature_preferences)
            ]
            if by_feature:
                filtered = by_feature

        if state.luxury_intent:
            by_luxury = [
                product
                for product in filtered
                if self._matches_luxury_intent(product, state)
            ]
            if len(by_luxury) >= 3:
                filtered = by_luxury

        return filtered

    def _collect_symbol_preferences(self, state: SessionState) -> dict[str, list[str]]:
        preferences = {
            "main_material": [],
            "stone_material": [],
            "style_preferences": [],
        }
        for rule_set, key in ((CONSTELLATION_RULES, state.constellation), (ZODIAC_RULES, state.zodiac)):
            if not key or key not in rule_set:
                continue
            rule = rule_set[key]
            for material in rule.get("main_material", []):
                if material not in preferences["main_material"]:
                    preferences["main_material"].append(material)
            for material in rule.get("stone_material", []):
                if material not in preferences["stone_material"]:
                    preferences["stone_material"].append(material)
            for style in rule.get("style_preferences", []):
                if style not in preferences["style_preferences"]:
                    preferences["style_preferences"].append(style)
        if state.excluded_main_material:
            preferences["main_material"] = [
                item for item in preferences["main_material"] if item not in state.excluded_main_material
            ]
        if state.excluded_stone_material:
            preferences["stone_material"] = [
                item for item in preferences["stone_material"] if item not in state.excluded_stone_material
            ]
        if state.excluded_style_preferences:
            preferences["style_preferences"] = [
                item for item in preferences["style_preferences"] if item not in state.excluded_style_preferences
            ]
        return preferences

    def _filter_products(
        self,
        *,
        products: list[dict[str, Any]],
        state: SessionState,
        tolerance: float | None,
    ) -> list[dict[str, Any]]:
        result = []
        for product in products:
            if not (product.get("product_qr_url") or product.get("product_image_url")):
                continue

            category = product.get("system_category") or ""
            if state.excluded_categories and any(excluded in category for excluded in state.excluded_categories):
                continue
            if state.category and not any(expected in category for expected in state.category):
                continue

            price = product.get("wholesale_price")
            if tolerance is not None and state.budget is not None and price is not None:
                if state.budget_flexibility is not None:
                    low = max(0.0, state.budget - state.budget_flexibility)
                    high = state.budget + state.budget_flexibility
                else:
                    low = state.budget * (1 - tolerance)
                    high = state.budget * (1 + tolerance)
                if not (low <= price <= high):
                    continue

            if state.main_material:
                if not self._matches_material_keywords(product, state.main_material):
                    continue

            if state.stone_material:
                if not self._matches_material_keywords(product, state.stone_material):
                    continue

            if state.excluded_main_material and self._matches_material_keywords(product, state.excluded_main_material):
                continue

            if state.excluded_stone_material and self._matches_material_keywords(product, state.excluded_stone_material):
                continue

            if state.excluded_style_preferences and self._matches_style_preferences(
                product,
                state.excluded_style_preferences,
            ):
                continue

            if state.excluded_feature_preferences and self._matches_feature_preferences(
                product,
                state.excluded_feature_preferences,
            ):
                continue

            if state.excluded_preferences:
                text = " ".join(
                    [
                        product.get("product_name") or "",
                        product.get("system_attributes") or "",
                        product.get("selling_points") or "",
                        product.get("main_material") or "",
                        product.get("stone_material") or "",
                    ]
                )
                if any(
                    excluded.replace("不要", "").replace("不想要", "").strip() in text
                    for excluded in state.excluded_preferences
                ):
                    continue

            result.append(product)
        return result

    def _find_nearest_budget_candidates(
        self,
        *,
        products: list[dict[str, Any]],
        state: SessionState,
        limit: int,
    ) -> list[dict[str, Any]]:
        candidates = self._filter_products(
            products=products,
            state=state,
            tolerance=None,
        )
        candidates = [product for product in candidates if product.get("wholesale_price") is not None]
        candidates = self._apply_priority_prefilters(candidates, state)
        candidates.sort(
            key=lambda product: (
                self._budget_distance(product, state.budget),
                product.get("wholesale_price") or float("inf"),
            )
        )
        return candidates[:limit]

    def has_structured_gift_target(self, state: SessionState) -> bool:
        return self._structured_gift_target(state) is not None

    def _budget_distance(self, product: dict[str, Any], budget: float | None) -> float:
        price = product.get("wholesale_price")
        if budget is None or price is None:
            return float("inf")
        return abs(price - budget)

    def _score_product(
        self,
        product: dict[str, Any],
        state: SessionState,
        profile: dict[str, int],
        symbol_preferences: dict[str, list[str]],
    ) -> int:
        score = 0
        category = product.get("system_category") or ""
        suitable_people = product.get("suitable_people") or ""
        attributes = product.get("system_attributes") or ""
        selling_points = product.get("selling_points") or ""
        luxury_flag = product.get("luxury_flag") or ""
        main_material = product.get("main_material") or ""
        stone_material = product.get("stone_material") or ""

        if state.category and any(expected in category for expected in state.category):
            score += profile["category"]

        structured_target = self._structured_gift_target(state)
        if structured_target and structured_target in suitable_people:
            score += profile["gift_target"]
        elif self._is_plain_self_wear(state):
            if not suitable_people:
                score += max(profile["gift_target"] // 2, 10)
            elif self._has_structured_audience(product):
                score -= profile["gift_target"]

        if state.luxury_intent:
            if self._matches_luxury_intent(product, state):
                score += profile["luxury"]

        if state.premium_upgrade_intent:
            score += self._score_premium_upgrade(product, state)

        if state.style_preferences and self._matches_style_preferences(product, state.style_preferences):
            score += profile["style"]

        if state.feature_preferences and self._matches_feature_preferences(product, state.feature_preferences):
            score += max(profile["style"] - 4, 10)

        if state.color_preferences and self._matches_primary_color_preferences(product, state.color_preferences):
            score += 24

        if state.main_material:
            expanded_main_keywords = self._expand_material_keywords(state.main_material)
            if any(keyword in main_material for keyword in expanded_main_keywords):
                score += profile["material"]
            elif any(keyword in stone_material for keyword in expanded_main_keywords):
                score += max(profile["material"] - 12, 18)
        elif symbol_preferences["main_material"] and any(
            keyword in main_material for keyword in symbol_preferences["main_material"]
        ):
            score += 10

        if state.stone_material:
            expanded_stone_keywords = self._expand_material_keywords(state.stone_material)
            if any(keyword in stone_material for keyword in expanded_stone_keywords):
                score += max(profile["material"] - 8, 16)
            elif any(keyword in main_material for keyword in expanded_stone_keywords):
                score += max(profile["material"] - 14, 14)
        elif symbol_preferences["stone_material"] and any(
            keyword in stone_material for keyword in symbol_preferences["stone_material"]
        ):
            score += 6

        if symbol_preferences["style_preferences"] and self._matches_style_preferences(
            product,
            symbol_preferences["style_preferences"],
        ):
            score += 6

        if state.image_features and self._matches_text_preferences(product, state.image_features):
            score += 16

        if product.get("discount") is not None:
            score += profile["discount"]

        return score

    def _structured_gift_target(self, state: SessionState) -> str | None:
        if state.gift_target == "妈妈" and state.age is not None and state.age >= 50:
            return "退休妈妈款"
        if state.gift_target == "自戴" and state.age is not None and state.age >= 50:
            return "退休妈妈款"
        if state.gift_target in {"男款", "退休妈妈款"}:
            return state.gift_target
        return None

    def _is_self_wear(self, state: SessionState) -> bool:
        return state.gift_target == "自戴"

    def _is_plain_self_wear(self, state: SessionState) -> bool:
        return self._is_self_wear(state) and self._structured_gift_target(state) is None

    def _has_structured_audience(self, product: dict[str, Any]) -> bool:
        suitable_people = product.get("suitable_people") or ""
        return any(tag in suitable_people for tag in ("男款", "退休妈妈款"))

    def _has_material_priority(self, state: SessionState) -> bool:
        return bool(state.main_material or state.stone_material)

    def _matches_requested_material(self, product: dict[str, Any], state: SessionState) -> bool:
        if state.main_material and not self._matches_material_keywords(product, state.main_material):
            return False
        if state.stone_material and not self._matches_material_keywords(product, state.stone_material):
            return False
        return True

    def _matches_material_keywords(self, product: dict[str, Any], keywords: list[str]) -> bool:
        expanded_keywords = self._expand_material_keywords(keywords)
        haystack = " ".join(
            [
                product.get("main_material") or "",
                product.get("stone_material") or "",
                product.get("product_name") or "",
                product.get("system_attributes") or "",
                product.get("selling_points") or "",
            ]
        )
        return any(keyword in haystack for keyword in expanded_keywords)

    def _matches_style_preferences(self, product: dict[str, Any], styles: list[str]) -> bool:
        return self._matches_text_preferences(product, styles)

    def _matches_feature_preferences(self, product: dict[str, Any], features: list[str]) -> bool:
        return self._matches_text_preferences(product, features)

    def _matches_text_preferences(self, product: dict[str, Any], preferences: list[str]) -> bool:
        haystack = " ".join(
            [
                product.get("product_name") or "",
                product.get("system_category") or "",
                product.get("system_attributes") or "",
                product.get("selling_points") or "",
                product.get("luxury_flag") or "",
                product.get("suitable_people") or "",
                product.get("main_material") or "",
                product.get("stone_material") or "",
            ]
        )
        return any(preference and preference in haystack for preference in preferences)

    def _matches_primary_color_preferences(self, product: dict[str, Any], colors: list[str]) -> bool:
        color_aliases = {
            "蓝色": ["蓝", "蓝色", "海蓝", "天蓝", "宝蓝", "蓝调", "蓝宝", "蓝水"],
            "绿色": ["绿", "绿色", "青绿", "翠绿", "墨绿"],
            "红色": ["红", "红色", "酒红", "玫红", "朱红"],
            "粉色": ["粉", "粉色", "樱花粉", "少女粉"],
            "紫色": ["紫", "紫色", "薰衣草紫"],
            "白色": ["白", "白色", "奶白", "米白"],
            "黑色": ["黑", "黑色", "曜黑"],
            "金色": ["金", "金色", "香槟金"],
            "银色": ["银", "银色"],
            "黄色": ["黄", "黄色", "鹅黄", "奶黄"],
            "橙色": ["橙", "橙色", "橘色", "橙黄"],
            "棕色": ["棕", "棕色", "咖色", "咖啡色"],
        }
        inferred_colors = [str(item).strip() for item in (product.get("_inferred_colors") or []) if str(item).strip()]
        if inferred_colors:
            primary_color = inferred_colors[0]
            for color in colors:
                variants = color_aliases.get(color, [color])
                if primary_color in variants or primary_color == color:
                    return True
            return False

        text_haystack = " ".join(
            [
                product.get("product_name") or "",
                product.get("main_material") or "",
                product.get("stone_material") or "",
                product.get("system_attributes") or "",
                product.get("selling_points") or "",
            ]
        )
        for color in colors:
            variants = color_aliases.get(color, [color])
            if any(variant in text_haystack for variant in variants):
                return True
        return False

    def _expand_material_keywords(self, keywords: list[str]) -> list[str]:
        expanded: list[str] = []
        for keyword in keywords:
            variants = MATERIAL_SYNONYMS.get(keyword, [keyword])
            for variant in variants:
                if variant not in expanded:
                    expanded.append(variant)
        return expanded

    def _score_premium_upgrade(self, product: dict[str, Any], state: SessionState) -> int:
        haystack = " ".join(
            [
                product.get("product_name") or "",
                product.get("main_material") or "",
                product.get("stone_material") or "",
                product.get("system_attributes") or "",
                product.get("selling_points") or "",
            ]
        )
        score = 0
        if any(keyword in haystack for keyword in PREMIUM_HINT_KEYWORDS):
            score += 20

        price = product.get("wholesale_price")
        if state.budget is not None and price is not None:
            ratio = min(price / state.budget, 1.0)
            score += int(ratio * 18)
        return score

    def _matches_luxury_intent(self, product: dict[str, Any], state: SessionState) -> bool:
        haystack = " ".join(
            [
                product.get("luxury_flag") or "",
                product.get("system_attributes") or "",
                product.get("selling_points") or "",
            ]
        )
        intent_keywords = list(state.luxury_intent) + list(state.style_preferences)
        if any(keyword in haystack for keyword in intent_keywords):
            return True
        return bool(product.get("luxury_flag"))
