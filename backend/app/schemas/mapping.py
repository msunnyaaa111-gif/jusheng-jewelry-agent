from __future__ import annotations

from pydantic import BaseModel, Field


class MappingTrainRequest(BaseModel):
    mapping_type: str
    phrase: str
    canonical_value: str


class MappingItem(BaseModel):
    mapping_type: str
    phrase: str
    canonical_value: str


class MappingListResponse(BaseModel):
    mappings: list[MappingItem] = Field(default_factory=list)


class DialogueTrainingExample(BaseModel):
    timestamp: str
    session_id: str
    text: str
    action: str
    extracted_conditions: dict


class DialogueTrainingLogResponse(BaseModel):
    examples: list[DialogueTrainingExample] = Field(default_factory=list)
