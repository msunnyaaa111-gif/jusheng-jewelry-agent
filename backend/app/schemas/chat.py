from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.session import SessionState


class ChatRequest(BaseModel):
    session_id: str = Field(description="Session ID. Keep it stable across follow-up turns.")
    user_id: str | None = Field(default=None, description="Optional user identifier.")
    text: str = Field(default="", description="User text input.")
    image_urls: list[str] = Field(default_factory=list, description="Image URL list, optional.")
    response_mode: str = Field(default="text", description="Response rendering mode, such as text or cards.")


class RecommendedProduct(BaseModel):
    product_code: str = Field(description="Product code")
    product_name: str = Field(description="Product name")
    category: str | None = Field(default=None, description="System category")
    group_price: float | None = Field(default=None, description="Retail/group price")
    wholesale_price: float | None = Field(default=None, description="Wholesale price")
    discount: float | None = Field(default=None, description="Discount ratio")
    main_material: str | None = Field(default=None, description="Main material")
    stone_material: str | None = Field(default=None, description="Stone material")
    style_text: str | None = Field(default=None, description="Style summary")
    reason_text: str = Field(description="Recommendation reason summary")
    advice_text: str | None = Field(default=None, description="Styling advice summary")
    qr_code: str | None = Field(default=None, description="Product QR image URL")
    image_url: str | None = Field(default=None, description="Product image URL")


class ChatResponse(BaseModel):
    session_id: str = Field(description="Session ID")
    action: str = Field(description="Turn action, such as GREETING / ASK_FOLLOWUP / RETRIEVE_AND_RECOMMEND")
    reply_text: str = Field(description="Final reply text")
    reply_source: str | None = Field(default=None, description="Reply source, such as llm / fallback / cards")
    purchase_advice: str | None = Field(default=None, description="Final purchase advice for product-card style rendering")
    followup_question: str | None = Field(default=None, description="Follow-up question if needed")
    recommended_products: list[RecommendedProduct] = Field(default_factory=list, description="Recommended product list")
    session_state: SessionState = Field(description="Current session state")


class CatalogSummaryResponse(BaseModel):
    loaded: bool = Field(description="Whether the catalog is loaded")
    workbook_path: str | None = Field(default=None, description="Current Excel workbook path")
    product_count: int = Field(description="Total product count")
    categories: list[str] = Field(default_factory=list, description="Detected categories")
