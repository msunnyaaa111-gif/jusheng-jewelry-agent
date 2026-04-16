from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConditionChange(BaseModel):
    field: str
    change_type: str
    old_value: Any = None
    new_value: Any = None


class SessionState(BaseModel):
    age: int | None = None
    budget: float | None = None
    budget_flexibility: float | None = None
    budget_unrestricted: bool = False
    category: list[str] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)
    main_material: list[str] = Field(default_factory=list)
    stone_material: list[str] = Field(default_factory=list)
    excluded_main_material: list[str] = Field(default_factory=list)
    excluded_stone_material: list[str] = Field(default_factory=list)
    color_preferences: list[str] = Field(default_factory=list)
    feature_preferences: list[str] = Field(default_factory=list)
    excluded_feature_preferences: list[str] = Field(default_factory=list)
    gift_target: str | None = None
    usage_scene: str | None = None
    style_preferences: list[str] = Field(default_factory=list)
    excluded_style_preferences: list[str] = Field(default_factory=list)
    luxury_intent: list[str] = Field(default_factory=list)
    constellation: str | None = None
    zodiac: str | None = None
    birthday: str | None = None
    image_features: list[str] = Field(default_factory=list)
    excluded_preferences: list[str] = Field(default_factory=list)
    premium_upgrade_intent: bool = False
    pending_followup_type: str | None = None
    pending_followup_options: list[str] = Field(default_factory=list)
    last_action: str | None = None
    last_retrieval_hash: str | None = None
    last_recommended_codes: list[str] = Field(default_factory=list)
    seen_recommended_codes: list[str] = Field(default_factory=list)

    def has_meaningful_conditions(self) -> bool:
        return any(
            [
                self.budget is not None,
                self.budget_unrestricted,
                self.age is not None,
                bool(self.category),
                bool(self.main_material),
                bool(self.stone_material),
                bool(self.excluded_main_material),
                bool(self.excluded_stone_material),
                bool(self.color_preferences),
                bool(self.feature_preferences),
                bool(self.excluded_feature_preferences),
                self.gift_target is not None,
                self.usage_scene is not None,
                bool(self.style_preferences),
                bool(self.excluded_style_preferences),
                bool(self.luxury_intent),
                self.constellation is not None,
                self.zodiac is not None,
                self.birthday is not None,
                bool(self.excluded_preferences),
            ]
        )
