from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import Settings


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
        payload = {
            "model": model or self.settings.longcat_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        client = await self._get_client()
        response = await client.post(
            self.settings.longcat_api_url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        return data["choices"][0]["message"]["content"]

    async def stream_chat_completion(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
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
        payload = {
            "model": model or self.settings.longcat_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        client = await self._get_client()
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
