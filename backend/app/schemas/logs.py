from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatLogEntry(BaseModel):
    timestamp: str = Field(description="Log timestamp")
    session_id: str = Field(description="Session ID")
    user_id: str | None = Field(default=None, description="Optional user ID")
    request_text: str = Field(description="User request text")
    image_urls: list[str] = Field(default_factory=list, description="Uploaded image URLs")
    response_mode: str = Field(description="Requested response mode")
    status: str = Field(description="Log status, such as ok or stream_fallback")
    duration_ms: int | None = Field(default=None, description="Request duration in milliseconds")
    error_message: str | None = Field(default=None, description="Error summary if the turn failed")
    action: str | None = Field(default=None, description="Resolved turn action")
    reply_source: str | None = Field(default=None, description="Reply source")
    reply_text: str | None = Field(default=None, description="Final reply text")
    followup_question: str | None = Field(default=None, description="Follow-up question if any")
    purchase_advice: str | None = Field(default=None, description="Purchase advice for card results")
    recommended_product_codes: list[str] = Field(default_factory=list, description="Recommended product codes")
    recommended_product_names: list[str] = Field(default_factory=list, description="Recommended product names")
    recommended_count: int = Field(description="Number of recommended products")
    session_state: dict[str, Any] = Field(default_factory=dict, description="Session state snapshot")


class ChatLogListResponse(BaseModel):
    logs: list[ChatLogEntry] = Field(default_factory=list, description="Recent user chat logs")
