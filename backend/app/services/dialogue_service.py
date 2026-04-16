from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.models.session import SessionState
from app.repositories.mapping_repository import MappingRepository
from app.schemas.chat import RecommendedProduct
from app.services.condition_parser import ConditionParser
from app.services.longcat_client import LongCatClient
from app.services.recommendation_service import RecommendationService


logger = logging.getLogger(__name__)


REPLY_SYSTEM_PROMPT = """
你是钜盛珠宝 AI 导购顾问，擅长把后端已经筛选出的真实商品，整理成专业、温暖、可直接发给客户的珠宝推荐文案。

你当前不是在自己调用工具，预算计算、商品筛选、排序和兜底都已经由后端完成。
你只能使用后端传给你的 session_state、products、followup_question、condition_changes 来生成最终回复。
严禁虚构商品、价格、材质、二维码、图片链接、库存、功效或保值承诺。

你会收到的商品字段通常包括：
- product_name：商品名称
- product_code：商品编码
- system_category：类别
- main_material：主材质
- stone_material：配石材质
- group_price：开团价/零售价
- wholesale_price：批发裸价
- discount：折扣
- product_qr_url：商品二维码图片
- product_image_url：商品展示图
- system_attributes：系统属性
- selling_points：产品优势卖点
- suitable_people：适合人群
- luxury_flag：显贵款标记

输出要求：
1. 你只输出 JSON，字段包括：reply_text, closing_text。
2. reply_text 必须是完整可读的 Markdown 文案，不要输出占位符，不要输出解释，不要输出 JSON 以外的文字。
3. 如果动作是 GREETING：
- 先欢迎
- 再说明你能按预算、送礼对象、款式、风格帮用户推荐
- 最后自然引导用户补充 1 到 2 个关键信息
4. 如果动作是 ASK_FOLLOWUP：
- 先承接用户已给出的条件
- 再只追问当前最关键的一步
- 不要模板化连环追问
5. 如果动作是 EXPLAIN_NO_RESULT：
- 明确说明当前条件下暂无完全匹配结果
- 给出温和的调整建议
- 不要编造可推荐商品
6. 如果动作是 RETRIEVE_AND_RECOMMEND 或 RERANK_AND_RECOMMEND：
- reply_text 使用下面的 Markdown 结构输出
- 最多只展示 3 个商品
- 每个商品都必须来自 products
- 不要写 [商品名称]、[类别] 这种占位文本

推荐文案结构：
## 推荐总述
[2-3句话，概括本次推荐思路，结合预算、送礼对象、风格、类目等条件]

## 商品推荐

### 1. 商品名称 商品编码
- **类别**：系统类别
- **材质**：主材质 + 配石材质

![商品图片](优先使用 product_qr_url；若为空则使用 product_image_url)

- **价格**：优先显示 group_price；若为空则显示 wholesale_price
- **批发裸价**：显示 wholesale_price
- **风格**：根据 system_attributes、selling_points、luxury_flag 概括为 1 句话

**推荐理由**：100-150 字，尽量包含材质特性、款式亮点、用户匹配、价值体现、情感关怀。

**搭配建议**：80-120 字，尽量包含适用场景、服饰搭配、佩戴技巧、简短保养提示。

## 购买建议
[1-2句话，总结如何选择，或邀请用户继续缩小范围]

额外约束：
- 如果 product_qr_url 和 product_image_url 都为空，则不要输出图片行。
- 如果 group_price 缺失，不要编造，直接用 wholesale_price 代替价格。
- 如果 stone_material 为空，材质就只写 main_material。
- “批发裸价”只显示金额，不要额外加括号说明。
- 如果商品数据里带有 _budget_fallback=true，表示这是“接近预算的可选款”，不要说成“都在预算内”。
- 如果用户刚刚修改了预算、款式、风格、星座、生肖等条件，要自然体现“已根据最新条件重新筛选”。
- 语气要专业、温暖、像真人导购，不要写成生硬模板。
"""

STREAM_REPLY_SYSTEM_PROMPT = """
你是钜盛珠宝 AI 导购顾问，擅长把后端已经筛选出的真实商品，整理成专业、温暖、适合直接发给客户的珠宝推荐话术。

你当前不是在自己调用工具，预算计算、商品筛选、排序和兜底都已经由后端完成。
你只能使用后端传给你的 session_state、products、followup_question、condition_changes 来生成最终回复。
严禁虚构商品、价格、材质、二维码、图片链接、库存、功效或保值承诺。

输出要求：
1. 只输出给客户看的纯文本，不要输出 JSON，不要输出 Markdown。
2. 不要使用 #、##、###、-、*、**、```、![图片](...) 这些 Markdown 符号。
3. 开场、追问、无结果说明都要自然、像真人导购，不要像固定模板。
4. 如果是推荐结果，请用纯文本分段输出，推荐结构如下：
推荐总述：
[2-3句话]

商品推荐：
1. 商品名称 商品编码
类别：...
材质：...
商品图片：优先使用 product_qr_url；若为空则使用 product_image_url；如果都没有就省略这行
价格：优先显示 group_price；若为空则显示 wholesale_price
批发裸价：显示 wholesale_price
风格：根据 system_attributes、selling_points、luxury_flag 概括
推荐理由：100-150字
搭配建议：80-120字

购买建议：
[1-2句话]

5. 如果商品带有 _budget_fallback=true，表述成“更接近预算的可选款”，不要说成“都在预算内”。
6. 如果用户刚刚修改了预算、款式、风格、星座、生肖等条件，要自然体现“已按最新条件重新筛选”。
"""

PRODUCT_COPY_SYSTEM_PROMPT = """
You are a senior Chinese jewelry sales copywriter.
Return JSON only with this shape:
{
  "products": [
    {
      "product_code": "string",
      "reason_text": "string",
      "advice_text": "string"
    }
  ],
  "purchase_advice": "string"
}

Rules:
- Write all copy in natural Chinese.
- Each product must have distinct copy based on its own materials, style, crowd fit, price band, and selling points.
- Do not repeat the same sentence pattern across products.
- reason_text should focus on why this exact item fits the user's needs, around 90-140 Chinese characters.
- advice_text should focus on styling, gifting, or daily-wear usage of this exact item, around 60-110 Chinese characters.
- purchase_advice should compare the shortlisted products and help the user decide, around 120-220 Chinese characters.
- In purchase_advice, refer to products by product_name, not by product_code, index, or numbering.
- Never invent fields, materials, prices, QR codes, or benefits not present in the payload.
- If some field is missing, write conservatively and stay grounded in the provided data.
"""


class DialogueService:
    def __init__(
        self,
        condition_parser: ConditionParser,
        recommendation_service: RecommendationService,
        longcat_client: LongCatClient,
        mapping_repository: MappingRepository | None = None,
    ) -> None:
        self.condition_parser = condition_parser
        self.recommendation_service = recommendation_service
        self.longcat_client = longcat_client
        self.mapping_repository = mapping_repository
        self.sessions: dict[str, SessionState] = {}
        self.histories: dict[str, list[dict[str, str]]] = {}

    def get_session_state(self, session_id: str) -> SessionState:
        return self.sessions.setdefault(session_id, SessionState())

    def _reset_session_state(self, session_id: str, *, hard: bool) -> SessionState:
        previous = self.get_session_state(session_id)
        if hard:
            state = SessionState()
        else:
            state = SessionState(
                constellation=previous.constellation,
                zodiac=previous.zodiac,
                birthday=previous.birthday,
            )
        self.sessions[session_id] = state
        return state

    def _append_history(self, session_id: str, role: str, content: str) -> None:
        self.histories.setdefault(session_id, []).append({"role": role, "content": content})
        self.histories[session_id] = self.histories[session_id][-12:]

    def _normalize_response_mode(self, response_mode: str | None) -> str:
        return "text" if str(response_mode or "").strip().lower() == "text" else "cards"

    async def handle_message(self, *, session_id: str, text: str, response_mode: str = "cards") -> dict[str, Any]:
        response_mode = self._normalize_response_mode(response_mode)
        turn = await self._prepare_turn(session_id=session_id, text=text)
        products = turn["recommended_products"]
        reply_source = "cards" if response_mode == "cards" else None
        if turn["action"] in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"} and products:
            products = await self._enrich_recommendation_copy(
                state=turn["state"],
                products=products,
            )

        if response_mode == "cards" and turn["action"] in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"} and products:
            reply_text = ""
        else:
            reply_text, reply_source = await self._generate_reply(
                action=turn["action"],
                text=text,
                state=turn["state"],
                parsed=turn["parsed"],
                products=products,
            )
        return self._finalize_turn(
            session_id=session_id,
            action=turn["action"],
            reply_text=reply_text,
            reply_source=reply_source,
            followup_question=turn["followup_question"],
            recommended_products=products,
            state=turn["state"],
        )

    async def stream_message(self, *, session_id: str, text: str, response_mode: str = "cards"):
        yield {"type": "status", "text": "正在理解您的需求，马上开始整理回复..."}
        response_mode = self._normalize_response_mode(response_mode)
        turn = await self._prepare_turn(session_id=session_id, text=text)
        action = turn["action"]
        state = turn["state"]
        parsed = turn["parsed"]
        products = turn["recommended_products"]
        followup_question = turn["followup_question"]

        if action in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"}:
            yield {"type": "status", "text": "正在筛选更合适的商品，马上为您整理成卡片推荐...", "display_mode": "cards"}
        elif action == "ASK_FOLLOWUP":
            yield {"type": "status", "text": "正在整理更贴合您的追问，通常几秒内就会开始输出...", "display_mode": "text"}
        elif action == "EXPLAIN_NO_RESULT":
            yield {"type": "status", "text": "正在核对当前条件下的匹配情况，通常几秒内就会开始输出...", "display_mode": "text"}

        if action in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"} and products:
            if response_mode == "cards":
                yield {"type": "status", "text": "已经筛到合适商品，正在补充每款亮点与购买建议...", "display_mode": "cards"}
            products = await self._enrich_recommendation_copy(
                state=state,
                products=products,
            )
            if response_mode == "cards":
                response = self._finalize_turn(
                    session_id=session_id,
                    action=action,
                    reply_text="",
                    reply_source="cards",
                    followup_question=followup_question,
                    recommended_products=products,
                    state=state,
                )
                yield {"type": "done", "response": response}
                return

        reply_text = ""
        reply_source = "llm"
        if self.longcat_client.settings.llm_enabled:
            payload = self._build_reply_payload(
                action=action,
                text=text,
                state=state,
                parsed=parsed,
                products=products,
            )
            max_tokens = 1000 if action in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"} else 260
            try:
                async for chunk in self.longcat_client.stream_chat_completion(
                    system_prompt=STREAM_REPLY_SYSTEM_PROMPT,
                    user_payload=payload,
                    temperature=0.4,
                    max_tokens=max_tokens,
                ):
                    if not chunk:
                        continue
                    reply_text += chunk
                    if action not in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"}:
                        yield {"type": "delta", "text": chunk}
            except Exception:
                logger.exception("Streaming reply generation failed; falling back", extra={"action": action})
                reply_text = ""

        if not reply_text.strip():
            reply_text, reply_source = await self._generate_reply(
                action=action,
                text=text,
                state=state,
                parsed=parsed,
                products=products,
            )
            if action in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"}:
                async for chunk in self._stream_formatted_reply(reply_text):
                    yield {"type": "delta", "text": chunk}
            else:
                yield {"type": "delta", "text": reply_text}
        elif action in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"}:
            reply_text = self._finalize_recommendation_reply(
                reply_text=reply_text,
                state=state,
                products=products,
            )
            async for chunk in self._stream_formatted_reply(reply_text):
                yield {"type": "delta", "text": chunk}

        reply_text = self._sanitize_reply_text(action, reply_text)
        response = self._finalize_turn(
            session_id=session_id,
            action=action,
            reply_text=reply_text,
            reply_source=reply_source,
            followup_question=followup_question,
            recommended_products=products,
            state=state,
        )
        yield {"type": "done", "response": response}

    async def _stream_formatted_reply(self, reply_text: str):
        for chunk in self._chunk_reply_text(reply_text):
            if not chunk:
                continue
            yield chunk
            await asyncio.sleep(0.03)

    def _chunk_reply_text(self, reply_text: str) -> list[str]:
        chunks: list[str] = []
        for block in reply_text.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            if len(block) <= 140:
                chunks.append(block + "\n\n")
                continue
            lines = block.splitlines()
            if len(lines) > 1:
                for line in lines:
                    line = line.rstrip()
                    if line:
                        chunks.append(line + "\n")
                chunks.append("\n")
                continue
            text = block
            while text:
                piece = text[:120]
                text = text[120:]
                chunks.append(piece)
            chunks.append("\n\n")
        if chunks and chunks[-1].endswith("\n\n"):
            chunks[-1] = chunks[-1].rstrip("\n")
        return chunks

    async def _prepare_turn(self, *, session_id: str, text: str) -> dict[str, Any]:
        state = self.get_session_state(session_id)
        history = self.histories.get(session_id, [])
        explicit_conditions = self.condition_parser.extract_explicit_conditions(text)

        reset_mode = self._detect_topic_reset(
            text=text,
            state=state,
            explicit_conditions=explicit_conditions,
        )
        if reset_mode:
            state = self._reset_session_state(session_id, hard=reset_mode == "hard")

        self._apply_pending_followup(state, text, explicit_conditions)

        parsed = await self.condition_parser.parse(
            message=text,
            session_state=state,
            recent_history=history,
        )
        self._append_history(session_id, "user", text)
        merged_conditions = self._combine_conditions(
            explicit_conditions,
            parsed.get("conditions", {}),
        )
        self._merge_conditions(
            state,
            merged_conditions,
            parsed.get("condition_changes", []),
        )

        retrieval_hash = self.recommendation_service.build_retrieval_hash(state)
        should_refresh = parsed.get("should_refresh_retrieval", False) or state.last_retrieval_hash != retrieval_hash
        action = parsed.get("action", "ASK_FOLLOWUP")
        if should_refresh:
            state.seen_recommended_codes = []

        recommended_products: list[dict[str, Any]] = []
        followup_question = parsed.get("followup_question")

        if action in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"}:
            if action == "RERANK_AND_RECOMMEND":
                recommended_products = await self.recommendation_service.search(
                    state,
                    exclude_product_codes=state.seen_recommended_codes,
                )
            elif should_refresh or not state.last_recommended_codes:
                recommended_products = await self.recommendation_service.search(state)
                state.last_retrieval_hash = retrieval_hash
            else:
                recommended_products = await self.recommendation_service.search(state)

            if not recommended_products:
                if action == "RERANK_AND_RECOMMEND" and state.seen_recommended_codes:
                    action = "EXPLAIN_NO_RESULT"
                    parsed["notes_for_backend"] = [
                        *(parsed.get("notes_for_backend") or []),
                        "no_more_fresh_recommendations",
                    ]
                alternative_category_followup = self._build_empty_result_alternative_followup(state)
                if action != "EXPLAIN_NO_RESULT" and alternative_category_followup:
                    action = "ASK_FOLLOWUP"
                    followup_question = alternative_category_followup
                    parsed["followup_question"] = alternative_category_followup
                    state.pending_followup_type = "premium_alternative_category"
                    state.pending_followup_options = self._suggest_alternative_categories(state)
                elif action != "EXPLAIN_NO_RESULT":
                    action = "EXPLAIN_NO_RESULT"
            else:
                current_codes = [item["product_code"] for item in recommended_products]
                state.last_recommended_codes = current_codes
                if action == "RERANK_AND_RECOMMEND":
                    state.seen_recommended_codes = list(dict.fromkeys([*state.seen_recommended_codes, *current_codes]))
                else:
                    state.seen_recommended_codes = current_codes
                state.last_retrieval_hash = retrieval_hash
                budget_gap_followup = self._build_budget_gap_followup(state, recommended_products)
                if budget_gap_followup:
                    action = "ASK_FOLLOWUP"
                    followup_question = budget_gap_followup
                    parsed["followup_question"] = budget_gap_followup
                    recommended_products = []
                    state.pending_followup_type = "budget_gap_upgrade"
                    state.pending_followup_options = []
                else:
                    alternative_category_followup = self._build_alternative_category_followup(
                        state,
                        recommended_products,
                    )
                    if alternative_category_followup:
                        action = "ASK_FOLLOWUP"
                        followup_question = alternative_category_followup
                        parsed["followup_question"] = alternative_category_followup
                        recommended_products = []
                        state.pending_followup_type = "premium_alternative_category"
                        state.pending_followup_options = self._suggest_alternative_categories(state)
                    else:
                        state.pending_followup_type = None
                        state.pending_followup_options = []
        elif action != "ASK_FOLLOWUP":
            state.pending_followup_type = None
            state.pending_followup_options = []

        if self.mapping_repository is not None:
            self.mapping_repository.log_dialogue_example(
                session_id=session_id,
                text=text,
                extracted_conditions=merged_conditions,
                action=action,
            )
        return {
            "state": state,
            "parsed": parsed,
            "action": action,
            "followup_question": followup_question if action == "ASK_FOLLOWUP" else None,
            "recommended_products": recommended_products,
        }

    def _detect_topic_reset(
        self,
        *,
        text: str,
        state: SessionState,
        explicit_conditions: dict[str, Any],
    ) -> str | None:
        normalized = text.strip().lower()
        if not normalized or not state.has_meaningful_conditions():
            return None
        if self._is_confirmation_like(text):
            return None

        hard_reset_markers = (
            "重新开始",
            "重新推荐",
            "清空重新",
            "当我前面没说",
            "前面作废",
            "重来",
        )
        if any(marker in text for marker in hard_reset_markers):
            return "hard"

        soft_reset_markers = (
            "重新看",
            "另外看看",
            "换一个",
            "换成",
            "再看看别的",
            "还有没有别的",
            "不送这个人了",
            "这次是给",
            "这次想买",
            "这次想看",
            "那如果换成",
        )
        if any(marker in text for marker in soft_reset_markers):
            return "soft"

        fresh_signal_count = self._count_explicit_core_signals(explicit_conditions)
        conflict_count = self._count_core_conflicts(state, explicit_conditions)
        if conflict_count >= 2:
            return "soft"
        if conflict_count >= 1 and fresh_signal_count >= 2:
            return "soft"
        return None

    def _is_confirmation_like(self, text: str) -> bool:
        normalized = text.strip().lower()
        if self._is_affirmative(normalized) or self._is_negative(normalized):
            return True
        short_followups = ("还是", "那就", "就看", "就要", "那耳环", "那项链", "那戒指", "那手链")
        return len(normalized) <= 10 and normalized.startswith(short_followups)

    def _count_explicit_core_signals(self, conditions: dict[str, Any]) -> int:
        count = 0
        if conditions.get("budget") is not None:
            count += 1
        if conditions.get("category"):
            count += 1
        if conditions.get("gift_target") is not None:
            count += 1
        if conditions.get("main_material") or conditions.get("stone_material"):
            count += 1
        if conditions.get("luxury_intent") or conditions.get("style_preferences"):
            count += 1
        return count

    def _count_core_conflicts(
        self,
        state: SessionState,
        conditions: dict[str, Any],
    ) -> int:
        conflicts = 0

        new_budget = conditions.get("budget")
        if new_budget is not None and state.budget is not None:
            budget_delta = abs(new_budget - state.budget)
            if budget_delta >= max(150.0, state.budget * 0.25):
                conflicts += 1

        new_categories = conditions.get("category") or []
        if new_categories and state.category and not any(item in state.category for item in new_categories):
            conflicts += 1

        new_target = conditions.get("gift_target")
        if new_target is not None and state.gift_target is not None and new_target != state.gift_target:
            conflicts += 1

        new_main = conditions.get("main_material") or []
        if new_main and state.main_material and not any(item in state.main_material for item in new_main):
            conflicts += 1

        new_stone = conditions.get("stone_material") or []
        if new_stone and state.stone_material and not any(item in state.stone_material for item in new_stone):
            conflicts += 1

        new_styles = set(conditions.get("style_preferences") or [])
        current_styles = set(state.style_preferences or [])
        new_luxury = set(conditions.get("luxury_intent") or [])
        current_luxury = set(state.luxury_intent or [])
        if (
            (new_styles and current_styles and new_styles.isdisjoint(current_styles))
            or (new_luxury and current_luxury and new_luxury.isdisjoint(current_luxury))
        ):
            conflicts += 1

        return conflicts

    async def _enrich_recommendation_copy(
        self,
        *,
        state: SessionState,
        products: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prepared_products = [dict(product) for product in products]
        fallback_products, fallback_purchase_advice = self._build_copy_fallbacks(
            state=state,
            products=prepared_products,
        )

        if not self.longcat_client.settings.llm_enabled:
            return fallback_products

        payload = {
            "session_state": {
                key: value
                for key, value in state.model_dump().items()
                if value not in (None, "", [], False)
            },
            "products": [
                {
                    "product_code": product.get("product_code"),
                    "product_name": product.get("product_name"),
                    "category": product.get("system_category"),
                    "group_price": product.get("group_price"),
                    "wholesale_price": product.get("wholesale_price"),
                    "main_material": product.get("main_material"),
                    "stone_material": product.get("stone_material"),
                    "style_text": self._build_style_text(product),
                    "selling_points": product.get("selling_points"),
                    "suitable_people": product.get("suitable_people"),
                    "luxury_flag": product.get("luxury_flag"),
                }
                for product in prepared_products[:3]
            ],
        }

        try:
            raw = await self.longcat_client.chat_completion(
                system_prompt=PRODUCT_COPY_SYSTEM_PROMPT,
                user_payload=payload,
                temperature=0.55,
                max_tokens=1200,
            )
            result = self.longcat_client.extract_json_block(raw)
        except Exception:
            logger.exception("Recommendation copy enrichment failed; using fallback copy")
            return fallback_products

        product_copy_map: dict[str, dict[str, str]] = {}
        for item in result.get("products", []):
            if not isinstance(item, dict):
                continue
            product_code = str(item.get("product_code") or "").strip()
            if not product_code:
                continue
            product_copy_map[product_code] = {
                "reason_text": str(item.get("reason_text") or "").strip(),
                "advice_text": str(item.get("advice_text") or "").strip(),
            }

        purchase_advice = str(result.get("purchase_advice") or "").strip() or fallback_purchase_advice

        for product in fallback_products:
            copy_item = product_copy_map.get(product.get("product_code", ""))
            if copy_item:
                product["_reason_text"] = copy_item.get("reason_text") or product.get("_reason_text")
                product["_advice_text"] = copy_item.get("advice_text") or product.get("_advice_text")
            product["_purchase_advice"] = purchase_advice

        return fallback_products

    def _build_copy_fallbacks(
        self,
        *,
        state: SessionState,
        products: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str]:
        purchase_advice = self._build_purchase_advice(state=state, products=products)
        for product in products:
            product["_reason_text"] = self._build_reason_detail(product, state)
            product["_advice_text"] = self._build_style_advice(product, state)
            product["_purchase_advice"] = purchase_advice
        return products, purchase_advice

    def _finalize_turn(
        self,
        *,
        session_id: str,
        action: str,
        reply_text: str,
        reply_source: str | None,
        followup_question: str | None,
        recommended_products: list[dict[str, Any]],
        state: SessionState,
    ) -> dict[str, Any]:
        purchase_advice = None
        if recommended_products:
            purchase_advice = (
                str(recommended_products[0].get("_purchase_advice") or "").strip() or None
            )
        self._append_history(session_id, "assistant", reply_text or purchase_advice or followup_question or "")
        state.last_action = action
        return {
            "action": action,
            "reply_text": reply_text,
            "reply_source": reply_source,
            "purchase_advice": purchase_advice,
            "followup_question": followup_question if action == "ASK_FOLLOWUP" else None,
            "recommended_products": [self._to_api_product(product, state) for product in recommended_products],
            "session_state": state,
        }

    def _combine_conditions(
        self,
        heuristic_conditions: dict[str, Any],
        parsed_conditions: dict[str, Any],
    ) -> dict[str, Any]:
        combined = dict(heuristic_conditions or {})
        for field, value in (parsed_conditions or {}).items():
            if value in (None, "", []):
                continue
            current = combined.get(field)
            if isinstance(current, list):
                merged_list = list(current)
                items = value if isinstance(value, list) else [value]
                for item in items:
                    if item not in merged_list:
                        merged_list.append(item)
                combined[field] = merged_list
            elif current not in (None, "", []):
                continue
            else:
                combined[field] = value
        return combined

    def _merge_conditions(
        self,
        state: SessionState,
        conditions: dict[str, Any],
        condition_changes: list[dict[str, Any]] | None = None,
    ) -> None:
        replace_fields = {
            change.get("field")
            for change in (condition_changes or [])
            if change.get("change_type") == "replace"
        }
        list_replace_fields = {
            field
            for field in replace_fields
            if field
            in {
                "category",
                "excluded_categories",
                "main_material",
                "stone_material",
                "excluded_main_material",
                "excluded_stone_material",
                "color_preferences",
                "feature_preferences",
                "excluded_feature_preferences",
                "style_preferences",
                "excluded_style_preferences",
                "luxury_intent",
                "image_features",
                "excluded_preferences",
            }
        }

        for field in list_replace_fields:
            setattr(state, field, [])

        excluded_categories = conditions.get("excluded_categories") or []
        if excluded_categories:
            merged_excluded = list(state.excluded_categories)
            for item in excluded_categories:
                if item not in merged_excluded:
                    merged_excluded.append(item)
            state.excluded_categories = merged_excluded
            if state.category:
                state.category = [item for item in state.category if item not in excluded_categories]

        categories = conditions.get("category") or []
        if categories and state.excluded_categories:
            state.excluded_categories = [
                item for item in state.excluded_categories if item not in categories
            ]

        excluded_main_material = conditions.get("excluded_main_material") or []
        if excluded_main_material:
            merged_excluded = list(state.excluded_main_material)
            for item in excluded_main_material:
                if item not in merged_excluded:
                    merged_excluded.append(item)
            state.excluded_main_material = merged_excluded
            if state.main_material:
                state.main_material = [item for item in state.main_material if item not in excluded_main_material]

        excluded_stone_material = conditions.get("excluded_stone_material") or []
        if excluded_stone_material:
            merged_excluded = list(state.excluded_stone_material)
            for item in excluded_stone_material:
                if item not in merged_excluded:
                    merged_excluded.append(item)
            state.excluded_stone_material = merged_excluded
            if state.stone_material:
                state.stone_material = [item for item in state.stone_material if item not in excluded_stone_material]

        excluded_style_preferences = conditions.get("excluded_style_preferences") or []
        if excluded_style_preferences:
            merged_excluded = list(state.excluded_style_preferences)
            for item in excluded_style_preferences:
                if item not in merged_excluded:
                    merged_excluded.append(item)
            state.excluded_style_preferences = merged_excluded
            if state.style_preferences:
                state.style_preferences = [item for item in state.style_preferences if item not in excluded_style_preferences]

        main_materials = conditions.get("main_material") or []
        if main_materials and state.excluded_main_material:
            state.excluded_main_material = [
                item for item in state.excluded_main_material if item not in main_materials
            ]

        stone_materials = conditions.get("stone_material") or []
        if stone_materials and state.excluded_stone_material:
            state.excluded_stone_material = [
                item for item in state.excluded_stone_material if item not in stone_materials
            ]

        style_preferences = conditions.get("style_preferences") or []
        if style_preferences and state.excluded_style_preferences:
            state.excluded_style_preferences = [
                item for item in state.excluded_style_preferences if item not in style_preferences
            ]

        excluded_feature_preferences = conditions.get("excluded_feature_preferences") or []
        if excluded_feature_preferences:
            merged_excluded = list(state.excluded_feature_preferences)
            for item in excluded_feature_preferences:
                if item not in merged_excluded:
                    merged_excluded.append(item)
            state.excluded_feature_preferences = merged_excluded
            if state.feature_preferences:
                state.feature_preferences = [item for item in state.feature_preferences if item not in excluded_feature_preferences]

        feature_preferences = conditions.get("feature_preferences") or []
        if feature_preferences and state.excluded_feature_preferences:
            state.excluded_feature_preferences = [
                item for item in state.excluded_feature_preferences if item not in feature_preferences
            ]

        for field, value in conditions.items():
            if value in (None, "", []):
                continue
            if field in {
                "excluded_categories",
                "excluded_main_material",
                "excluded_stone_material",
                "excluded_feature_preferences",
                "excluded_style_preferences",
            }:
                continue
            current = getattr(state, field, None)
            if isinstance(current, list):
                merged = list(current)
                for item in value:
                    if item not in merged:
                        merged.append(item)
                setattr(state, field, merged)
            else:
                setattr(state, field, value)

    def _apply_pending_followup(
        self,
        state: SessionState,
        text: str,
        explicit_conditions: dict[str, Any],
    ) -> None:
        if state.pending_followup_type != "budget_gap_upgrade":
            if state.pending_followup_type == "premium_alternative_category":
                self._apply_alternative_category_followup(state, text)
            return

        normalized = text.strip().lower()
        if self._is_affirmative(normalized):
            state.pending_followup_type = None
            state.pending_followup_options = []
            state.premium_upgrade_intent = True
            self._append_unique(explicit_conditions, "style_preferences", "高级感")
            self._append_unique(explicit_conditions, "style_preferences", "精致")
            self._append_unique(explicit_conditions, "luxury_intent", "轻奢")
            self._append_unique(explicit_conditions, "luxury_intent", "显贵")
            return

        if self._is_negative(normalized):
            state.pending_followup_type = None
            state.pending_followup_options = []
            state.premium_upgrade_intent = False

    def _apply_alternative_category_followup(self, state: SessionState, text: str) -> None:
        normalized = text.strip().lower()
        if self._is_affirmative(normalized):
            options = list(state.pending_followup_options)
            if options:
                state.category = options
                state.excluded_categories = [
                    item for item in state.excluded_categories if item not in options
                ]
            state.pending_followup_type = None
            state.pending_followup_options = []
            state.premium_upgrade_intent = True
            return

        if self._is_negative(normalized):
            state.pending_followup_type = None
            state.pending_followup_options = []

    def _append_unique(self, conditions: dict[str, Any], field: str, value: str) -> None:
        current = conditions.setdefault(field, [])
        if value not in current:
            current.append(value)

    def _is_affirmative(self, text: str) -> bool:
        affirmative_texts = {
            "要",
            "好的",
            "好",
            "可以",
            "行",
            "行的",
            "嗯",
            "嗯嗯",
            "是的",
            "对",
            "对的",
            "那就这样",
        }
        return text in affirmative_texts or text.startswith(("要", "好", "可以", "行", "那就", "那你就"))

    def _is_negative(self, text: str) -> bool:
        negative_texts = {
            "不要",
            "不用",
            "不用了",
            "先不用",
            "算了",
            "不了",
            "不需要",
        }
        return text in negative_texts or text.startswith(("不要", "不用", "不了", "算了"))

    async def _generate_reply(
        self,
        *,
        action: str,
        text: str,
        state: SessionState,
        parsed: dict[str, Any],
        products: list[dict[str, Any]],
    ) -> tuple[str, str]:
        if self.longcat_client.settings.llm_enabled:
            max_tokens = 1000 if action in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"} else 260
            payload = self._build_reply_payload(
                action=action,
                text=text,
                state=state,
                parsed=parsed,
                products=products,
            )
            try:
                raw = await self.longcat_client.chat_completion(
                    system_prompt=REPLY_SYSTEM_PROMPT,
                    user_payload=payload,
                    temperature=0.4,
                    max_tokens=max_tokens,
                )
                result = self.longcat_client.extract_json_block(raw)
                reply_text = (result.get("reply_text") or "").strip()
                closing = (result.get("closing_text") or "").strip()
                if reply_text:
                    if action in {"RETRIEVE_AND_RECOMMEND", "RERANK_AND_RECOMMEND"}:
                        reply_text = self._finalize_recommendation_reply(
                            reply_text=reply_text,
                            state=state,
                            products=products,
                        )
                        closing = ""
                    else:
                        reply_text = self._sanitize_reply_text(action, reply_text)
                    closing = self._sanitize_reply_text(action, closing) if closing else closing
                    final_reply = f"{reply_text}\n\n{closing}".strip() if closing else reply_text
                    return final_reply, "llm"
            except Exception:
                logger.exception("Reply generation failed; using fallback", extra={"action": action})

        return self._build_rich_fallback_reply(action=action, state=state, parsed=parsed, products=products), "fallback"

    def _build_rich_fallback_reply(
        self,
        *,
        action: str,
        state: SessionState,
        parsed: dict[str, Any],
        products: list[dict[str, Any]],
    ) -> str:
        if action == "GREETING":
            return (
                "您好！欢迎来到钜盛珠宝，我是您的专属导购顾问，很高兴为您服务。\n\n"
                "我可以根据预算、送礼对象、款式偏好和佩戴场景，帮您更快筛到合适的珠宝。\n\n"
                "您这次更偏向自己佩戴，还是送人呢？如果方便的话，也可以直接告诉我大概预算。"
            )

        if action == "ASK_FOLLOWUP":
            question = parsed.get("followup_question") or "您方便再告诉我一下预算，或者更想看的款式方向吗？"
            context_parts: list[str] = []
            if state.budget is not None:
                context_parts.append(f"预算大概在 {self._format_price(state.budget)} 左右")
            if state.gift_target == "自戴":
                context_parts.append("这次更偏向自己日常佩戴")
            elif state.gift_target:
                context_parts.append(f"这次主要是给{state.gift_target}挑选")
            if state.category:
                context_parts.append(f"我会优先围绕{state.category[0]}来帮您筛选")

            if context_parts:
                return (
                    f"您好，我先记下来了：{'，'.join(context_parts)}。\n\n"
                    f"这样我会更容易帮您缩小范围。{question}"
                )
            return (
                "您好！欢迎来到钜盛珠宝，我这边已经收到您的需求了。\n\n"
                f"为了更快帮您筛到更合适的款式，{question}"
            )

        if action == "EXPLAIN_NO_RESULT":
            notes = parsed.get("notes_for_backend") or []
            if "no_more_fresh_recommendations" in notes:
                return (
                    "我刚按您刚才这组条件继续往下筛了一轮，这一轮能补充的新款已经比较少了，所以不是系统一直重复同一批，"
                    "而是当前条件下更匹配的款式基本已经看完了。\n\n"
                    "如果您愿意，我可以马上换个方向继续帮您找，比如放宽一点预算、换材质，或者改成更日常/更显贵的风格。"
                )
            return (
                "我刚刚按您现在的条件帮您筛了一轮，当前完全匹配的款式还比较少。\n\n"
                "如果您愿意，我可以帮您稍微放宽一点预算范围，或者换成相近的材质、风格或品类，再继续给您补一轮更贴近的推荐。"
            )

        if products:
            return self._render_detailed_recommendation(state=state, products=products)

        return "您好，我已经收到您的需求了。您可以继续告诉我预算、款式偏好或送礼对象，我再帮您更精准地筛选。"

    def _build_reply_payload(
        self,
        *,
        action: str,
        text: str,
        state: SessionState,
        parsed: dict[str, Any],
        products: list[dict[str, Any]],
    ) -> dict[str, Any]:
        compact_state = {
            key: value
            for key, value in state.model_dump().items()
            if value not in (None, "", [], False)
        }
        compact_products = [
            {
                "product_name": product.get("product_name"),
                "product_code": product.get("product_code"),
                "system_category": product.get("system_category"),
                "main_material": product.get("main_material"),
                "stone_material": product.get("stone_material"),
                "group_price": product.get("group_price"),
                "wholesale_price": product.get("wholesale_price"),
                "product_qr_url": product.get("product_qr_url"),
                "product_image_url": product.get("product_image_url"),
                "system_attributes": product.get("system_attributes"),
                "selling_points": product.get("selling_points"),
                "suitable_people": product.get("suitable_people"),
                "luxury_flag": product.get("luxury_flag"),
                "_budget_fallback": product.get("_budget_fallback"),
            }
            for product in products[:3]
        ]
        return {
            "action": action,
            "current_user_message": text,
            "session_state": compact_state,
            "condition_changes": parsed.get("condition_changes", []),
            "followup_question": parsed.get("followup_question"),
            "notes_for_backend": parsed.get("notes_for_backend", []),
            "products": compact_products,
        }

    def _fallback_reply(
        self,
        *,
        action: str,
        state: SessionState,
        parsed: dict[str, Any],
        products: list[dict[str, Any]],
    ) -> str:
        if action == "GREETING":
            return (
                "您好呀，我可以帮您按预算、款式、送礼对象和风格来挑更合适的珠宝。"
                "您这次是想自己佩戴，还是送人呢？如果方便的话，也可以告诉我大概预算。"
            )

        if action == "ASK_FOLLOWUP":
            question = parsed.get("followup_question") or "您方便再告诉我一下预算或想看的款式吗？"
            return f"我先了解到了您的部分需求，这样我会更好帮您筛选。{question}"

        if action == "EXPLAIN_NO_RESULT":
            notes = parsed.get("notes_for_backend") or []
            if "no_more_fresh_recommendations" in notes:
                return (
                    "我刚按您刚才这组条件继续往下筛了一轮，这一轮能补充的新款已经比较少了，所以不是系统一直重复同一批，"
                    "而是当前条件下更匹配的款式基本已经看完了。"
                    "如果您愿意，我可以继续按预算、材质或风格帮您换个方向再找一轮。"
                )
            return (
                "我刚按您现在的条件帮您筛了一轮，当前命中的款式比较少。"
                "如果您愿意，我可以帮您稍微放宽一点预算区间，或者换一个相近材质，再给您补一轮更合适的推荐。"
            )

        if products:
            return self._render_detailed_recommendation(state=state, products=products)

        return "我已经收到您的需求了，您可以继续告诉我预算、款式或送礼对象，我来帮您更精准地筛选。"

    def _sanitize_reply_text(self, action: str, reply_text: str) -> str:
        sanitized = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", r"商品图片：\1", reply_text)
        sanitized = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1：\2", sanitized)
        sanitized = re.sub(r"\*\*(.*?)\*\*", r"\1", sanitized)
        sanitized = sanitized.replace("`", "")

        sanitized_lines = []
        for line in sanitized.splitlines():
            if re.fullmatch(r"\s*[-*_]{3,}\s*", line):
                continue
            line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
            line = re.sub(r"^\s*[-*]\s+", "", line)
            sanitized_lines.append(line)

        sanitized = "\n".join(sanitized_lines)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        return sanitized.strip()

    def _finalize_recommendation_reply(
        self,
        *,
        reply_text: str,
        state: SessionState,
        products: list[dict[str, Any]],
    ) -> str:
        return self._render_detailed_recommendation(state=state, products=products)

    def _is_detailed_recommendation_reply(self, reply_text: str) -> bool:
        required_markers = ("推荐总述", "商品推荐", "推荐理由", "搭配建议", "购买建议")
        return all(marker in reply_text for marker in required_markers)

    def _render_detailed_recommendation(
        self,
        *,
        state: SessionState,
        products: list[dict[str, Any]],
    ) -> str:
        if not products:
            return "我已经收到您的需求了，您可以继续告诉我预算、款式或送礼对象，我来帮您更精准地筛选。"

        lines = [
            "推荐总述：",
            self._build_recommendation_overview(state=state, products=products),
            "",
            "商品推荐：",
            "",
        ]

        for index, product in enumerate(products[:3], 1):
            lines.extend(self._render_product_block(index=index, product=product, state=state))
            lines.append("")

        lines.extend(
            [
                "购买建议：",
                self._build_purchase_advice(state=state, products=products),
            ]
        )
        return "\n".join(lines).strip()

    def _build_recommendation_overview(
        self,
        *,
        state: SessionState,
        products: list[dict[str, Any]],
    ) -> str:
        match_count = len(products[:3])
        parts: list[str] = []

        if state.budget is not None:
            parts.append(f"这次我先按您 {self._format_price(state.budget)} 左右的预算")
        else:
            parts.append("我先按您刚刚补充的条件")

        if state.gift_target == "自戴":
            parts.append("和日常自戴的方向")
        elif state.gift_target == "妈妈":
            parts.append("和给妈妈挑礼物的方向")
        elif state.gift_target:
            parts.append(f"和给{state.gift_target}挑选的方向")

        if state.category:
            parts.append(f"重新筛了 {match_count} 款更贴近{state.category[0]}需求的商品")
        else:
            parts.append(f"重新筛了 {match_count} 款更贴近当前需求的商品")

        if match_count < 3:
            parts.append(f"，当前条件下先找到 {match_count} 款更匹配的选项")

        closing = "这一轮我优先按当前条件做了严格筛选，下面这几款会更贴近您现在的需求。"
        return "".join(parts) + "，" + closing

        parts = []
        if state.budget is not None:
            parts.append(f"这次我先按您 {self._format_price(state.budget)} 左右的预算")
        else:
            parts.append("我先按您刚刚补充的条件")

        if state.gift_target == "自戴":
            parts.append("和日常自戴的方向")
        elif state.gift_target == "妈妈":
            parts.append("和给妈妈挑礼物的方向")
        elif state.gift_target:
            parts.append(f"和{state.gift_target}场景")

        if state.category:
            parts.append(f"重新筛了 {len(products[:3])} 款更贴近{state.category[0]}需求的商品")
        else:
            parts.append(f"重新筛了 {len(products[:3])} 款更贴近当前需求的商品")

        closing = "这轮我优先按批发裸价做了筛选，下面这几款会更贴近您现在的需求。"
        return "".join(parts) + "，" + closing

    def _render_product_block(
        self,
        *,
        index: int,
        product: dict[str, Any],
        state: SessionState,
    ) -> list[str]:
        image_url = self._resolve_media_url(
            product.get("product_qr_url") or product.get("product_image_url")
        )
        lines = [
            f"{index}. {product.get('product_name', '珠宝商品')}  {product.get('product_code', '')}".rstrip(),
            "",
            f"类别：{product.get('system_category') or '待确认'}",
            "",
            f"材质：{self._build_material_text(product)}",
        ]
        if image_url:
            lines.append("")
            lines.append(f"商品图片：{image_url}")
        lines.extend(
            [
                "",
                f"价格：{self._format_price(product.get('group_price') or product.get('wholesale_price'))}",
                "",
                f"批发裸价：{self._format_price(product.get('wholesale_price'))}",
                "",
                f"风格：{self._build_style_text(product)}",
                "",
                f"推荐理由：{product.get('_reason_text') or self._build_reason_detail(product, state)}",
                "",
                f"搭配建议：{product.get('_advice_text') or self._build_style_advice(product, state)}",
            ]
        )
        return lines

    def _resolve_media_url(self, value: Any) -> str:
        if not value:
            return ""
        url = str(value).strip()
        if not url:
            return ""
        if url.startswith(("http://", "https://")):
            return url
        return url

    def _build_material_text(self, product: dict[str, Any]) -> str:
        main_material = product.get("main_material") or "待确认"
        stone_material = product.get("stone_material") or ""
        if stone_material:
            return f"{main_material}、{stone_material}"
        return str(main_material)

    def _build_style_text(self, product: dict[str, Any]) -> str:
        parts = []
        for value in (
            product.get("system_attributes") or "",
            product.get("selling_points") or "",
            product.get("luxury_flag") or "",
        ):
            value = str(value).strip()
            if value and value not in parts:
                parts.append(value)
        return "，".join(parts[:2]) or "整体风格自然耐看，比较适合当前需求"

    def _build_reason_detail(self, product: dict[str, Any], state: SessionState) -> str:
        parts = [self._build_reason(product, state)]
        main_material = product.get("main_material")
        if main_material:
            parts.append(f"{main_material}本身会让佩戴质感更稳，也更耐看。")
        selling_points = product.get("selling_points")
        if selling_points:
            parts.append(f"这款更出彩的地方在于：{self._summarize_selling_points(selling_points)}。")
        sentences = []
        for part in parts:
            cleaned = str(part or "").strip().rstrip("。；; ")
            if cleaned:
                sentences.append(cleaned)
        return "。".join(sentences) + ("。" if sentences else "")

    def _summarize_selling_points(self, selling_points: Any) -> str:
        text = str(selling_points or "").strip()
        if not text:
            return ""
        text = text.replace("\n", " ").replace("\r", " ")
        for sep in ("。", "；", ";", "！", "？"):
            if sep in text:
                text = text.split(sep, 1)[0]
                break
        text = text.strip(" ，,。；;")
        if len(text) > 26:
            text = text[:26].rstrip(" ，,。；;") + "…"
        return text

    def _build_style_advice(self, product: dict[str, Any], state: SessionState) -> str:
        category = product.get("system_category") or ""
        if "项链" in category or "吊坠" in category:
            return "比较适合日常通勤、约会或轻正式场合佩戴，搭配简洁领口会更显线条感，平时注意避免和硬物磕碰。"
        if "戒指" in category:
            return "适合通勤、聚会或日常点缀使用，搭配简洁穿着会更突出细节感，佩戴后记得避免频繁接触化学清洁用品。"
        return "比较适合日常佩戴、通勤或休闲场景，搭配简洁穿着会更耐看，平时注意避免暴晒和磕碰，方便保持光泽。"

    def _build_purchase_advice(self, state: SessionState, products: list[dict[str, Any]]) -> str:
        if products:
            generated = str(products[0].get("_purchase_advice") or "").strip()
            if generated:
                return generated
        product_names = [str(product.get("product_name") or "").strip() for product in products if product.get("product_name")]
        if any(product.get("_budget_fallback") for product in products):
            if len(product_names) >= 2:
                return f"如果您更在意预算贴合度，可以先从 {product_names[0]} 和 {product_names[1]} 里做比较；如果想让我继续往更显贵一点或更日常百搭一点的方向细分，我也可以继续帮您缩小范围。"
            return "这几款里有接近您预算的可选方向，如果您愿意，我也可以继续帮您往更显贵一点或更日常百搭一点的方向再细分。"
        if len(product_names) >= 3:
            return f"如果您偏重日常百搭，可以优先看 {product_names[0]}；如果更在意设计感或送礼氛围，可以把 {product_names[1]} 和 {product_names[2]} 作为重点对比。我也可以继续按显贵感、材质偏好或佩戴场景，再帮您缩小到最适合的一两款。"
        if len(product_names) >= 2:
            return f"这两款里如果您更重视日常佩戴，可以先看 {product_names[0]}；如果更在意风格表达，也可以重点比较 {product_names[1]}。如果您愿意，我还可以继续帮您再缩小一轮。"
        return "如果您愿意，我可以继续按显贵感、日常百搭或送礼场景，再帮您从这几款里缩小到更适合的一两款。"

    def _format_price(self, value: Any) -> str:
        if value in (None, ""):
            return "待确认"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if number.is_integer():
            return f"{int(number)}元"
        return f"{number:.2f}".rstrip("0").rstrip(".") + "元"

    def _build_reason(self, product: dict[str, Any], state: SessionState) -> str:
        reasons = []
        if product.get("_budget_fallback") and state.budget is not None:
            reasons.append(f"这是当前款式里更接近您 {int(state.budget)} 元预算的选择")
        if state.category and product.get("system_category"):
            reasons.append(f"款式方向和您想看的{product['system_category']}比较匹配")
        if state.gift_target == "自戴":
            reasons.append("更适合日常自戴、通勤或休闲场景来搭配")
        elif state.gift_target and product.get("suitable_people"):
            reasons.append("适合作为送礼场景来参考")
        if state.luxury_intent:
            reasons.append("整体会更有精致和轻奢感")
        return "；".join(reasons[:3]) or "整体风格和当前需求比较贴合"

    def _build_budget_gap_followup(
        self,
        state: SessionState,
        products: list[dict[str, Any]],
    ) -> str | None:
        if state.budget is None or not products:
            return None
        if state.premium_upgrade_intent:
            return None
        if not any(product.get("_budget_fallback") for product in products):
            return None

        priced_products = [product for product in products if product.get("wholesale_price") is not None]
        if not priced_products:
            return None

        max_price = max(product["wholesale_price"] for product in priced_products)
        if max_price > state.budget * 0.6:
            return None

        category_text = "、".join(state.category) if state.category else "这类款式"
        return (
            f"我先帮您看了一轮，当前货盘里更接近的 {category_text} 价位还是偏低一些。"
            "如果您想看更高档一点的材质或工艺款，我可以继续往 K金、黄金或更精致镶嵌方向再帮您筛一轮，要不要我这样找给您？"
        )

    def _build_alternative_category_followup(
        self,
        state: SessionState,
        products: list[dict[str, Any]],
    ) -> str | None:
        if state.budget is None or not products or not state.premium_upgrade_intent:
            return None
        if not any(product.get("_budget_fallback") for product in products):
            return None

        priced_products = [product for product in products if product.get("wholesale_price") is not None]
        if not priced_products:
            return None

        max_price = max(product["wholesale_price"] for product in priced_products)
        if max_price > state.budget * 0.45:
            return None

        alternatives = self._suggest_alternative_categories(state)
        if not alternatives:
            return None

        category_text = "、".join(state.category) if state.category else "当前这类款式"
        alternative_text = "、".join(alternatives)
        gift_suffix = "礼赠款" if state.gift_target and state.gift_target != "自戴" else "款"
        return (
            f"{category_text} 目前高价位货不算多。"
            f"要不要我顺带给您看同预算更合适的 {alternative_text}{gift_suffix}？"
        )

    def _build_empty_result_alternative_followup(self, state: SessionState) -> str | None:
        if not state.premium_upgrade_intent:
            return None
        alternatives = self._suggest_alternative_categories(state)
        if not alternatives:
            return None

        category_text = "、".join(state.category) if state.category else "当前这类款式"
        alternative_text = "、".join(alternatives)
        gift_suffix = "礼赠款" if state.gift_target and state.gift_target != "自戴" else "款"
        return (
            f"{category_text} 这个方向目前高档款选择比较少。"
            f"要不要我顺带给您看看同预算更合适的 {alternative_text}{gift_suffix}？"
        )

    def _suggest_alternative_categories(self, state: SessionState) -> list[str]:
        current_categories = set(state.category)
        if len(current_categories) != 1:
            return []
        if "耳环" in current_categories:
            return ["项链", "戒指"]
        if "戒指" in current_categories:
            return ["项链", "耳环"]
        if "手链" in current_categories or "手串" in current_categories:
            return ["项链", "戒指"]
        return []

    def _to_api_product(self, product: dict[str, Any], state: SessionState) -> RecommendedProduct:
        return RecommendedProduct(
            product_code=product["product_code"],
            product_name=product["product_name"],
            category=product.get("system_category"),
            group_price=product.get("group_price"),
            wholesale_price=product.get("wholesale_price"),
            discount=product.get("discount"),
            main_material=product.get("main_material"),
            stone_material=product.get("stone_material"),
            style_text=self._build_style_text(product),
            reason_text=product.get("_reason_text") or self._build_reason_detail(product, state),
            advice_text=product.get("_advice_text") or self._build_style_advice(product, state),
            qr_code=product.get("product_qr_url"),
            image_url=product.get("product_image_url"),
        )
