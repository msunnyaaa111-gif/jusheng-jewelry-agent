from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from app.models.session import ConditionChange, SessionState
from app.repositories.mapping_repository import MappingRepository
from app.services.longcat_client import LongCatClient


CONSTELLATIONS = [
    "白羊座",
    "金牛座",
    "双子座",
    "巨蟹座",
    "狮子座",
    "处女座",
    "天秤座",
    "天蝎座",
    "射手座",
    "摩羯座",
    "水瓶座",
    "双鱼座",
]

ZODIACS = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

CATEGORY_ALIASES = {
    "手绳": "手链",
    "手饰": "手链",
    "手镯": "手链",
    "镯子": "手链",
    "串子": "手链",
    "腕饰": "手链",
    "手串": "手链",
    "手链": "手链",
    "锁骨链": "项链",
    "颈链": "项链",
    "链子": "项链",
    "脖链": "项链",
    "颈饰": "项链",
    "项坠": "项链",
    "挂坠": "项链",
    "项链": "项链",
    "吊坠": "项链",
    "吊牌": "项链",
    "耳夹": "耳环",
    "耳坠": "耳环",
    "耳钉": "耳环",
    "耳饰": "耳环",
    "耳圈": "耳环",
    "耳线": "耳环",
    "耳骨夹": "耳环",
    "耳骨钉": "耳环",
    "耳环": "耳环",
    "对戒": "戒指",
    "尾戒": "戒指",
    "指环": "戒指",
    "戒圈": "戒指",
    "戒指": "戒指",
}

GIFT_TARGET_KEYWORDS = {
    "男款": [
        "男友", "男朋友", "送男友", "送男朋友", "给男友", "给男朋友",
        "男票", "男伴", "另一半", "对象男生", "对象是男生",
        "老公", "丈夫", "先生", "送老公", "送丈夫", "给老公", "给丈夫",
        "爸爸", "父亲", "老爸", "送爸爸", "给爸爸", "送父亲", "给父亲",
        "男性朋友", "男性长辈", "兄弟", "弟弟", "哥哥", "男生", "男士", "他戴", "他用",
    ],
    "妈妈": [
        "妈妈", "母亲", "我妈", "我妈妈", "送妈妈", "送给妈妈", "送我妈", "给妈妈", "给我妈",
    ],
    "退休妈妈款": [
        "婆婆", "岳母", "丈母娘", "阿姨", "姨妈", "姑妈", "婶婶", "舅妈",
        "长辈", "女性长辈", "中老年女性", "退休妈妈", "家里长辈", "母亲节送妈妈",
    ],
    "女友": [
        "女友", "女朋友", "对象", "对象戴", "对象用", "送对象",
        "女票", "另一半", "对象是女生", "老婆", "妻子", "太太", "媳妇", "未婚妻", "她戴", "她用",
    ],
    "闺蜜": ["闺蜜", "姐妹", "姐妹淘", "好姐妹", "小姐妹", "朋友", "女同事"],
    "自戴": [
        "自己戴", "我自己戴", "自己带", "我自己带", "自戴", "给自己", "自己用", "自用",
        "自己佩戴", "我戴", "我用", "自己留着", "留给自己", "我自己留着",
        "我佩戴", "我自己用", "我日常戴", "日常自己戴",
    ],
}

STYLE_KEYWORDS = [
    "简约",
    "温柔",
    "大气",
    "国风",
    "中国风",
    "东方",
    "新中式",
    "通勤",
    "精致",
    "高级感",
    "轻奢",
    "显贵",
    "百搭",
    "日常",
    "小众",
    "复古",
    "时尚",
    "秀气",
    "耐看",
    "气质",
    "优雅",
    "干练",
    "知性",
    "甜美",
    "少女",
    "清冷",
    "冷淡风",
    "法式",
    "通透",
]

LUXURY_KEYWORDS = {
    "轻奢": [
        "轻奢", "精致", "有质感", "小轻奢", "精美一点", "细节好一点",
        "质感好", "精致感", "轻熟", "低调高级", "小贵气",
    ],
    "显贵": [
        "显贵", "看起来贵", "高级感", "大气", "贵气", "上档次", "有档次", "看着贵",
        "性价比", "预算友好", "便宜但好看", "划算", "值一点", "值这个价", "物超所值", "超值", "高性价比",
        "不廉价", "不low", "像大牌", "大牌感", "贵妇感", "精贵", "有面子", "体面", "拿得出手",
    ],
}

MAIN_MATERIAL_KEYWORDS = [
    "黄金", "金饰", "金子", "足金",
    "K金", "18K", "18k", "18k金",
    "水晶", "粉晶", "白水晶", "紫水晶", "黄水晶", "茶晶", "发晶", "钛晶", "超七", "草莓晶",
    "沉香", "沉香木", "野生沉香", "奇楠", "棋楠", "降真香", "老山檀",
    "蜜蜡", "花珀", "琥珀",
    "南红", "玛瑙", "红玛瑙",
    "碧玉", "青玉", "晴水", "黄口",
    "绿松石", "青金石", "海蓝宝",
    "朱砂", "天珠", "天珠玛瑙", "金丝玉", "玉髓", "碧玺", "虎眼石",
    "猛犸象牙", "象牙", "小叶紫檀", "淡水珍珠", "贝壳珠", "贝壳", "血珀",
    "石英岩玉", "石英岩质玉", "菩提根", "绿幽灵", "月光石", "蓝晶石",
    "珍珠",
    "和田玉", "玉", "玉石",
    "红宝石", "翡翠",
    "银", "纯银", "925银", "s925", "S925",
]
STONE_MATERIAL_KEYWORDS = [
    "锆石", "钻石", "红宝石", "珍珠", "925银", "碎钻", "主石",
    "沉香", "奇楠", "棋楠", "降真香", "老山檀",
    "蜜蜡", "花珀", "琥珀",
    "南红", "玛瑙", "红玛瑙",
    "绿松石", "青金石", "海蓝宝",
    "朱砂", "天珠", "金丝玉", "玉髓", "碧玺", "虎眼石",
    "猛犸象牙", "小叶紫檀", "淡水珍珠", "贝壳珠", "血珀",
    "石英岩玉", "石英岩质玉", "菩提根", "绿幽灵", "月光石", "蓝晶石",
]

PARSER_SYSTEM_PROMPT = """
你是珠宝导购智能体的语义理解引擎。
你只负责输出结构化 JSON，不要输出任何解释。
你必须识别：
1. 用户当前意图
2. 是否新增、修改、撤回了条件
3. 是否需要重检索
4. 结构化条件字段

返回 JSON，字段包括：
intent, action, confidence, conditions, condition_changes, should_refresh_retrieval, needs_followup, followup_question, notes_for_backend

action 只能从以下值选择：
GREETING, ASK_FOLLOWUP, RETRIEVE_AND_RECOMMEND, RERANK_AND_RECOMMEND, EXPLAIN_NO_RESULT, CLARIFY_CONFLICT, GENERAL_REPLY
"""


class ConditionParser:
    def __init__(
        self,
        longcat_client: LongCatClient,
        mapping_repository: MappingRepository | None = None,
    ) -> None:
        self.longcat_client = longcat_client
        self.mapping_repository = mapping_repository

    async def parse(
        self,
        *,
        message: str,
        session_state: SessionState,
        recent_history: list[dict[str, str]],
    ) -> dict[str, Any]:
        heuristic = self._heuristic_parse(message=message, session_state=session_state)

        if not self.longcat_client.settings.llm_enabled:
            return heuristic

        if self._should_use_heuristic_only(message=message, heuristic=heuristic):
            return heuristic

        payload = {
            "conversation_context": recent_history[-4:],
            "current_session_state": self._compact_session_state(session_state),
            "current_user_message": message,
            "heuristic_result": heuristic,
        }
        try:
            raw = await self.longcat_client.chat_completion(
                system_prompt=PARSER_SYSTEM_PROMPT,
                user_payload=payload,
                temperature=0.1,
                max_tokens=1200,
            )
            parsed = self._normalize_llm_result(self.longcat_client.extract_json_block(raw))
            return self._merge_llm_result(heuristic, parsed)
        except Exception:
            return heuristic

    def _should_use_heuristic_only(self, *, message: str, heuristic: dict[str, Any]) -> bool:
        normalized = message.strip()
        action = heuristic.get("action")
        if action in {"GREETING", "ASK_FOLLOWUP"}:
            return True

        if normalized.lower() in {"好", "好的", "可以", "行", "嗯", "嗯嗯", "要", "不要", "不用", "ok", "okay"}:
            return True

        conditions = heuristic.get("conditions") or {}
        direct_signal_count = sum(
            [
                1 if conditions.get("budget") is not None else 0,
                1 if conditions.get("category") else 0,
                1 if conditions.get("excluded_categories") else 0,
                1 if conditions.get("main_material") else 0,
                1 if conditions.get("stone_material") else 0,
                1 if conditions.get("gift_target") is not None else 0,
                1 if conditions.get("style_preferences") else 0,
                1 if conditions.get("luxury_intent") else 0,
                1 if conditions.get("constellation") is not None else 0,
                1 if conditions.get("zodiac") is not None else 0,
                1 if conditions.get("birthday") is not None else 0,
            ]
        )

        if direct_signal_count >= 1 and len(normalized) <= 80:
            return True

        return False

    def _compact_session_state(self, session_state: SessionState) -> dict[str, Any]:
        return {
            key: value
            for key, value in session_state.model_dump().items()
            if value not in (None, "", [], False)
        }

    def _normalize_llm_result(self, llm_result: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(llm_result)
        conditions = dict(normalized.get("conditions") or {})

        for list_field in [
            "category",
            "excluded_categories",
            "main_material",
            "stone_material",
            "style_preferences",
            "luxury_intent",
            "image_features",
            "excluded_preferences",
        ]:
            value = conditions.get(list_field)
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                cleaned = [self._canonicalize_condition(list_field, item) for item in value]
                conditions[list_field] = [item for item in cleaned if item]

        for scalar_field in ["gift_target", "usage_scene", "constellation", "zodiac", "birthday"]:
            value = conditions.get(scalar_field)
            if isinstance(value, str):
                conditions[scalar_field] = self._canonicalize_condition(scalar_field, value)

        normalized["conditions"] = conditions

        if not isinstance(normalized.get("condition_changes"), list):
            normalized["condition_changes"] = None

        notes = normalized.get("notes_for_backend")
        if isinstance(notes, str) and notes.strip():
            normalized["notes_for_backend"] = [notes.strip()]
        elif not isinstance(notes, list):
            normalized["notes_for_backend"] = None

        return normalized

    def _canonicalize_condition(self, field: str, value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None

        if field == "gift_target":
            matched_target = self._match_gift_target(text, field_only=True)
            if matched_target:
                return matched_target
            return text

        if field in {"category", "excluded_categories"}:
            for source, target in self._category_aliases().items():
                if source in text or text == target:
                    return target
            return text

        if field in {"luxury_intent", "style_preferences", "main_material", "stone_material"}:
            phrase_map = self._learned_phrase_map(field)
            if text in phrase_map:
                return phrase_map[text]

        return text

    def extract_explicit_conditions(self, message: str) -> dict[str, Any]:
        text = self._normalize_text(message)
        budget = self._extract_budget(text)
        budget_flexibility = self._extract_budget_flexibility(text)
        return {
            "age": self._extract_age(text),
            "budget": budget,
            "budget_flexibility": budget_flexibility,
            "category": self._extract_categories(text),
            "excluded_categories": self._extract_negated_categories(text),
            "main_material": self._extract_main_materials(text),
            "stone_material": self._extract_stone_materials(text),
            "gift_target": self._extract_gift_target(text),
            "usage_scene": None,
            "style_preferences": self._extract_style_preferences(text),
            "luxury_intent": self._extract_luxury_intent(text),
            "constellation": self._extract_constellation(text),
            "zodiac": self._extract_zodiac(text),
            "birthday": self._extract_birthday(text),
            "excluded_preferences": self._extract_exclusions(text),
        }

    def _heuristic_parse(self, *, message: str, session_state: SessionState) -> dict[str, Any]:
        text = self._normalize_text(message)
        conditions = self.extract_explicit_conditions(text)

        meaningful = any(
            [
                conditions["age"] is not None,
                conditions["budget"] is not None,
                conditions["category"],
                conditions["excluded_categories"],
                conditions["main_material"],
                conditions["stone_material"],
                conditions["gift_target"] is not None,
                conditions["style_preferences"],
                conditions["luxury_intent"],
                conditions["constellation"] is not None,
                conditions["zodiac"] is not None,
                conditions["birthday"] is not None,
                conditions["excluded_preferences"],
            ]
        )

        greeting = text in {"你好", "您好", "hi", "hello", "在吗"} or ("你好" in text and not meaningful)
        changes = self._detect_changes(session_state, conditions)
        refresh = any(
            change.field
            in {
                "age",
                "budget",
                "category",
                "main_material",
                "stone_material",
                "gift_target",
                "constellation",
                "zodiac",
                "birthday",
            }
            for change in changes
        )

        if greeting and not session_state.has_meaningful_conditions():
            action = "GREETING"
            intent = "greeting"
            needs_followup = True
        elif meaningful or session_state.has_meaningful_conditions():
            enough = self._has_enough_for_recommendation(conditions, session_state)
            action = "RETRIEVE_AND_RECOMMEND" if enough else "ASK_FOLLOWUP"
            intent = "ask_recommendation" if enough else "provide_conditions"
            needs_followup = not enough
        else:
            action = "ASK_FOLLOWUP"
            intent = "casual_chat"
            needs_followup = True

        followup = self._pick_followup_question(session_state=session_state, conditions=conditions) if needs_followup else None

        return {
            "intent": intent,
            "action": action,
            "confidence": 0.72,
            "conditions": conditions,
            "condition_changes": [change.model_dump() for change in changes],
            "should_refresh_retrieval": refresh,
            "needs_followup": needs_followup,
            "followup_question": followup,
            "notes_for_backend": [],
        }

    def _normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text or "")
        normalized = normalized.replace("\ufeff", "").replace("\u200b", "").replace("\xa0", " ")
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _merge_llm_result(self, heuristic: dict[str, Any], llm_result: dict[str, Any]) -> dict[str, Any]:
        merged = heuristic.copy()
        for key, value in llm_result.items():
            if key == "conditions":
                continue
            if value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value

        if "conditions" in llm_result:
            merged_conditions = heuristic.get("conditions", {}).copy()
            for field, value in (llm_result["conditions"] or {}).items():
                if value is None:
                    continue
                if isinstance(value, list) and not value:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                current_value = merged_conditions.get(field)
                if isinstance(current_value, list):
                    combined = list(current_value)
                    items = value if isinstance(value, list) else [value]
                    for item in items:
                        if item not in combined:
                            combined.append(item)
                    merged_conditions[field] = combined
                elif current_value not in (None, "", []):
                    continue
                else:
                    merged_conditions[field] = value
            merged["conditions"] = merged_conditions
        return merged

    def _extract_budget(self, text: str) -> float | None:
        # Remove birthday/date fragments first so years like "2005年" are not misread as budgets.
        sanitized = re.sub(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?", " ", text)

        range_match = re.search(
            r"(\d{2,6})\s*(?:-|—|–|到|至|~)\s*(\d{2,6})\s*(?:元|块)?(?:\s*(?:区间|之间|左右))?",
            sanitized,
        )
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            if low > high:
                low, high = high, low
            if high >= 100:
                return round((low + high) / 2, 2)

        patterns = [
            r"(?:预算|价位|预算是|预算在|预算改成|改成|控制在|大概|大约)\s*(\d{2,6})(?:\s*(?:元|块))?(?:\s*(?:左右|以内|以下|上下))?",
            r"(\d{2,6})\s*(?:元|块)(?:\s*(?:左右|以内|以下|上下))?",
            r"(\d{2,6})\s*(?:左右|以内|以下|上下)",
            r"(\d{2,6})\s*预算",
        ]

        for pattern in patterns:
            match = re.search(pattern, sanitized)
            if not match:
                continue
            value = float(match.group(1))
            if value < 100:
                continue
            return value
        return None

    def _extract_budget_flexibility(self, text: str) -> float | None:
        sanitized = re.sub(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?", " ", text)
        range_match = re.search(
            r"(\d{2,6})\s*(?:-|—|–|到|至|~)\s*(\d{2,6})\s*(?:元|块)?(?:\s*(?:区间|之间|左右))?",
            sanitized,
        )
        if not range_match:
            return None
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        if low > high:
            low, high = high, low
        if high < 100:
            return None
        return round((high - low) / 2, 2)

    def _extract_categories(self, text: str) -> list[str]:
        negated = set(self._extract_negated_categories(text))
        hits = []
        for source, target in self._category_aliases().items():
            if target in negated:
                continue
            if source in text and target not in hits:
                hits.append(target)
        return hits

    def _extract_negated_categories(self, text: str) -> list[str]:
        negated = []
        negative_prefixes = ["不要", "不想要", "不想看", "别要", "别看", "不要再看", "不看"]
        for source, target in self._category_aliases().items():
            if target in negated:
                continue
            if any(f"{prefix}{source}" in text for prefix in negative_prefixes):
                negated.append(target)
        return negated

    def _extract_keywords(self, text: str, keywords: list[str]) -> list[str]:
        hits = [keyword for keyword in keywords if keyword in text]
        return list(dict.fromkeys(hits))

    def _extract_main_materials(self, text: str) -> list[str]:
        return self._extract_mapped_terms(text, MAIN_MATERIAL_KEYWORDS, "main_material")

    def _extract_stone_materials(self, text: str) -> list[str]:
        return self._extract_mapped_terms(text, STONE_MATERIAL_KEYWORDS, "stone_material")

    def _extract_style_preferences(self, text: str) -> list[str]:
        return self._extract_mapped_terms(text, STYLE_KEYWORDS, "style_preferences")

    def _extract_mapped_terms(
        self,
        text: str,
        defaults: list[str],
        mapping_type: str,
    ) -> list[str]:
        hits = self._extract_keywords(text, defaults)
        for phrase, canonical in self._learned_phrase_map(mapping_type).items():
            if phrase in text and canonical not in hits:
                hits.append(canonical)
        return hits

    def _extract_gift_target(self, text: str) -> str | None:
        explicit_age = self._extract_age(text)
        matched_target = self._match_gift_target(text)
        if matched_target:
            return matched_target
        if explicit_age is not None and explicit_age >= 50 and self._mentions_female_age_context(text):
            return "自戴"
        return None

    def _match_gift_target(self, text: str, *, field_only: bool = False) -> str | None:
        normalized = self._normalize_text(text)
        if not normalized:
            return None

        if self._is_self_wear_expression(normalized, field_only=field_only):
            return "自戴"

        for label, keywords in self._gift_target_keywords().items():
            if any(keyword in normalized for keyword in keywords):
                return label

        return None

    def _is_self_wear_expression(self, text: str, *, field_only: bool = False) -> bool:
        direct_terms = (
            "自戴",
            "自用",
            "给自己",
            "给我自己",
            "送给自己",
            "送给我自己",
            "买给自己",
            "买给我自己",
            "留给自己",
            "留给我自己",
            "自己佩戴",
            "自己戴",
            "自己带",
            "自己用",
            "自己留着",
            "我自己戴",
            "我自己带",
            "我自己用",
            "我自己留着",
            "我日常戴",
            "日常自己戴",
        )
        if any(term in text for term in direct_terms):
            return True

        if field_only and text in {"自己", "我自己", "本人"}:
            return True

        contextual_patterns = (
            r"(?:送|买|挑|选|留|拿|配)?给我自己(?:用|戴|带|留着|佩戴)?",
            r"(?:送|买|挑|选|留|拿|配)?给自己(?:用|戴|带|留着|佩戴)?",
            r"我自己(?:用|戴|带|留着|佩戴)",
            r"自己(?:用|戴|带|留着|佩戴)",
        )
        return any(re.search(pattern, text) for pattern in contextual_patterns)

    def _extract_luxury_intent(self, text: str) -> list[str]:
        result = []
        for label, keywords in self._luxury_keywords().items():
            if any(keyword in text for keyword in keywords):
                result.append(label)
        return result

    def _extract_constellation(self, text: str) -> str | None:
        for item in CONSTELLATIONS:
            if item in text:
                return item
        birthday = self._extract_birthday(text)
        if birthday:
            return self._infer_constellation_from_birthday(birthday)
        return None

    def _extract_zodiac(self, text: str) -> str | None:
        match = re.search(r"属([鼠牛虎兔龙蛇马羊猴鸡狗猪])", text)
        if match:
            return match.group(1)
        return None

    def _extract_birthday(self, text: str) -> str | None:
        match = re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)", text)
        if match:
            return match.group(1)

        compact = re.search(r"(?:生日是?|生日[:：]?)\s*(\d{4})\b", text)
        if compact:
            raw = compact.group(1)
            month = int(raw[:2])
            day = int(raw[2:])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{month:02d}-{day:02d}"

        md_match = re.search(r"(?:生日是?|生日[:：]?)\s*(\d{1,2})[./-月](\d{1,2})日?", text)
        if md_match:
            month = int(md_match.group(1))
            day = int(md_match.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{month:02d}-{day:02d}"
        return None

    def _extract_age(self, text: str) -> int | None:
        birthday = self._extract_birthday(text)
        if birthday:
            year_match = re.match(r"(\d{4})", birthday)
            if year_match:
                birth_year = int(year_match.group(1))
                age = date.today().year - birth_year
                if 1 <= age <= 120:
                    return age

        for pattern in (r"(\d{1,3})\s*周岁", r"(\d{1,3})\s*岁"):
            match = re.search(pattern, text)
            if match:
                age = int(match.group(1))
                if 1 <= age <= 120:
                    return age

        for pattern in (r"(\d{2})多岁", r"(\d{2})岁以上"):
            match = re.search(pattern, text)
            if match:
                age = int(match.group(1))
                if 1 <= age <= 120:
                    return age
        return None

    def _infer_constellation_from_birthday(self, birthday: str) -> str | None:
        month_day_match = re.search(r"(\d{1,2})[-/月](\d{1,2})", birthday)
        if not month_day_match:
            month_day_match = re.search(r"\d{4}[-/年](\d{1,2})[-/月](\d{1,2})", birthday)
        if not month_day_match:
            return None

        month = int(month_day_match.group(1))
        day = int(month_day_match.group(2))
        if (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return "白羊座"
        if (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return "金牛座"
        if (month == 5 and day >= 21) or (month == 6 and day <= 21):
            return "双子座"
        if (month == 6 and day >= 22) or (month == 7 and day <= 22):
            return "巨蟹座"
        if (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return "狮子座"
        if (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return "处女座"
        if (month == 9 and day >= 23) or (month == 10 and day <= 23):
            return "天秤座"
        if (month == 10 and day >= 24) or (month == 11 and day <= 22):
            return "天蝎座"
        if (month == 11 and day >= 23) or (month == 12 and day <= 21):
            return "射手座"
        if (month == 12 and day >= 22) or (month == 1 and day <= 19):
            return "摩羯座"
        if (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return "水瓶座"
        if (month == 2 and day >= 19) or (month == 3 and day <= 20):
            return "双鱼座"
        return None

    def _mentions_female_age_context(self, text: str) -> bool:
        female_keywords = (
            "妈妈",
            "母亲",
            "阿姨",
            "婆婆",
            "岳母",
            "丈母娘",
            "女性",
            "女的",
            "女款",
            "妇女",
            "中老年女性",
        )
        self_keywords = ("我自己", "自戴", "自己戴", "自己带", "自用", "给自己")
        return any(keyword in text for keyword in female_keywords) or any(keyword in text for keyword in self_keywords)

    def _needs_mother_age_followup(self, *, conditions: dict[str, Any], session_state: SessionState) -> bool:
        gift_target = conditions.get("gift_target") or session_state.gift_target
        age = conditions.get("age") or session_state.age
        return gift_target == "妈妈" and age is None

    def _extract_exclusions(self, text: str) -> list[str]:
        result = []
        patterns = ["不要", "不想要", "别太"]
        for pattern in patterns:
            if pattern in text:
                result.append(text)
                break
        return result

    def _detect_changes(self, session_state: SessionState, conditions: dict[str, Any]) -> list[ConditionChange]:
        changes: list[ConditionChange] = []
        current = session_state.model_dump()
        for field, value in conditions.items():
            old_value = current.get(field)
            if value in (None, [], ""):
                continue
            if old_value in (None, [], ""):
                changes.append(
                    ConditionChange(field=field, change_type="append", old_value=old_value, new_value=value)
                )
            elif old_value != value:
                changes.append(
                    ConditionChange(field=field, change_type="replace", old_value=old_value, new_value=value)
                )
        return changes

    def _has_enough_for_recommendation(self, conditions: dict[str, Any], session_state: SessionState) -> bool:
        budget = conditions.get("budget") or session_state.budget
        category = conditions.get("category") or session_state.category
        material = (
            conditions.get("main_material")
            or session_state.main_material
            or conditions.get("stone_material")
            or session_state.stone_material
        )
        gift_target = conditions.get("gift_target") or session_state.gift_target
        style = conditions.get("style_preferences") or session_state.style_preferences
        luxury = conditions.get("luxury_intent") or session_state.luxury_intent
        if self._needs_mother_age_followup(conditions=conditions, session_state=session_state):
            return False

        has_budget = budget is not None
        has_category = bool(category)
        has_material = bool(material)
        has_target = gift_target is not None
        has_style = bool(style) or bool(luxury)

        # If the user only gives budget + category, keep one more follow-up turn
        # so we can refine by gifting target, material, or style before recommending.
        if has_budget and has_category and not (has_material or has_target or has_style):
            return False

        detailed_signal_count = sum([has_category, has_material, has_target, has_style])
        if has_budget and detailed_signal_count >= 1:
            return True
        if detailed_signal_count >= 3:
            return True
        return False

    def _pick_followup_question(self, *, session_state: SessionState, conditions: dict[str, Any]) -> str:
        category = conditions.get("category") or session_state.category
        budget = conditions.get("budget") or session_state.budget
        gift_target = conditions.get("gift_target") or session_state.gift_target
        material = (
            conditions.get("main_material")
            or session_state.main_material
            or conditions.get("stone_material")
            or session_state.stone_material
        )
        style = conditions.get("style_preferences") or session_state.style_preferences
        luxury = conditions.get("luxury_intent") or session_state.luxury_intent

        if self._needs_mother_age_followup(conditions=conditions, session_state=session_state):
            return "方便告诉我佩戴者大概年龄吗？如果是50岁以上的女性，我会优先按退休妈妈款来帮您筛选。"
        if not category:
            return "您更想看项链、手链、耳饰还是戒指呢？"
        if category and material and budget is None:
            return "这类材质和款式我已经记下了，方便告诉我大概预算区间吗？这样我能先帮您筛掉不合适的款。"
        if category and budget is not None and gift_target is None:
            return "这次您是自己佩戴，还是送女友、妈妈、闺蜜或男友呢？我可以按人群帮您再细分。"
        if gift_target is None:
            return "这次您是自己佩戴，还是送女友、妈妈或闺蜜呢？"
        if budget is None:
            return "方便告诉我大概预算区间吗？这样我可以更快帮您筛到合适的款。"
        if not material:
            return "材质上您会更偏黄金、K金、珍珠、和田玉还是红宝石这类方向呢？"
        if not style and not luxury:
            return "风格上您更想要显贵一点、日常百搭一点，还是偏温柔精致一点呢？"
        return "您更喜欢简约、温柔、显贵还是通勤百搭一点的风格呢？"

    def _category_aliases(self) -> dict[str, str]:
        return {**CATEGORY_ALIASES, **self._learned_phrase_map("category")}

    def _gift_target_keywords(self) -> dict[str, list[str]]:
        merged = {key: list(value) for key, value in GIFT_TARGET_KEYWORDS.items()}
        for phrase, canonical in self._learned_phrase_map("gift_target").items():
            merged.setdefault(canonical, [])
            if phrase not in merged[canonical]:
                merged[canonical].append(phrase)
        return merged

    def _luxury_keywords(self) -> dict[str, list[str]]:
        merged = {key: list(value) for key, value in LUXURY_KEYWORDS.items()}
        for phrase, canonical in self._learned_phrase_map("luxury_intent").items():
            merged.setdefault(canonical, [])
            if phrase not in merged[canonical]:
                merged[canonical].append(phrase)
        return merged

    def _learned_phrase_map(self, mapping_type: str) -> dict[str, str]:
        if not self.mapping_repository:
            return {}
        return self.mapping_repository.get_phrase_map(mapping_type)
