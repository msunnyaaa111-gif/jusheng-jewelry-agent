from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import Settings


logger = logging.getLogger(__name__)


class LongCatClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=45.0)
        return self._client

    async def chat_completion(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        image_inputs: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        model: str | None = None,
    ) -> str:
        if not self.settings.llm_enabled:
            raise RuntimeError("LONGCAT_API_KEY 未配置。")

        headers = {
            "Authorization": f"Bearer {self.settings.longcat_api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_request_payload(
            system_prompt=system_prompt,
            user_payload=user_payload,
            image_inputs=image_inputs,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            stream=False,
        )

        client = await self._get_client()
        try:
            response = await client.post(
                self.settings.longcat_api_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            body_preview = (exc.response.text or "")[:500] if exc.response is not None else ""
            logger.warning(
                "LongCat chat_completion failed with status=%s body=%s",
                exc.response.status_code if exc.response is not None else "unknown",
                body_preview,
            )
            raise
        except Exception:
            logger.exception("LongCat chat_completion request failed")
            raise

        return data["choices"][0]["message"]["content"]

    async def stream_chat_completion(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        image_inputs: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        model: str | None = None,
    ):
        if not self.settings.llm_enabled:
            raise RuntimeError("LONGCAT_API_KEY 未配置。")

        headers = {
            "Authorization": f"Bearer {self.settings.longcat_api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_request_payload(
            system_prompt=system_prompt,
            user_payload=user_payload,
            image_inputs=image_inputs,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            stream=True,
        )

        client = await self._get_client()
        try:
            async with client.stream(
                "POST",
                self.settings.longcat_api_url,
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
        except httpx.HTTPStatusError as exc:
            body_preview = ""
            if exc.response is not None:
                try:
                    body_preview = exc.response.text[:500]
                except Exception:
                    try:
                        body_preview = (await exc.response.aread()).decode("utf-8", errors="replace")[:500]
                    except Exception:
                        body_preview = ""
            logger.warning(
                "LongCat stream_chat_completion failed with status=%s body=%s",
                exc.response.status_code if exc.response is not None else "unknown",
                body_preview,
            )
            raise
        except Exception:
            logger.exception("LongCat stream_chat_completion request failed")
            raise

    @staticmethod
    def extract_json_block(raw_text: str) -> dict[str, Any]:
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _build_request_payload(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        image_inputs: list[str] | None,
        temperature: float,
        max_tokens: int,
        model: str | None,
        stream: bool,
    ) -> dict[str, Any]:
        resolved_model = model or self.settings.longcat_model
        user_text = json.dumps(user_payload, ensure_ascii=False)

        if self._uses_omni_format(resolved_model):
            user_content: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": user_text,
                }
            ]
            for image_input in image_inputs or []:
                if not image_input:
                    continue
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_input,
                        },
                    }
                )
            return {
                "model": resolved_model,
                "messages": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": system_prompt,
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ],
                "temperature": max(temperature, 0.01),
                "max_tokens": max_tokens,
                "stream": stream,
                "output_modalities": ["text"],
            }

        if image_inputs:
            raise ValueError(f"Model {resolved_model} does not support image inputs.")

        return {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_text,
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    @staticmethod
    def _uses_omni_format(model_name: str) -> bool:
        return "omni" in model_name.lower()

    @staticmethod
    def supports_image_inputs(model_name: str) -> bool:
        return LongCatClient._uses_omni_format(model_name)
