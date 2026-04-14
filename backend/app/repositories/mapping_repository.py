from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings


class MappingRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.data_dir = self.settings.backend_root / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.mapping_path = self.data_dir / "learned_mappings.json"
        self.dialogue_log_path = self.data_dir / "mapping_training_log.jsonl"

    def list_mappings(self) -> list[dict[str, str]]:
        return self._load_payload()["mappings"]

    def add_mapping(self, *, mapping_type: str, phrase: str, canonical_value: str) -> dict[str, Any]:
        payload = self._load_payload()
        normalized_phrase = phrase.strip()
        normalized_canonical = canonical_value.strip()

        for item in payload["mappings"]:
            if (
                item["mapping_type"] == mapping_type
                and item["phrase"] == normalized_phrase
            ):
                item["canonical_value"] = normalized_canonical
                self._save_payload(payload)
                return item

        new_item = {
            "mapping_type": mapping_type,
            "phrase": normalized_phrase,
            "canonical_value": normalized_canonical,
        }
        payload["mappings"].append(new_item)
        self._save_payload(payload)
        return new_item

    def remove_invalid_mappings(self) -> None:
        payload = self._load_payload()
        payload["mappings"] = [
            item
            for item in payload["mappings"]
            if "?" not in item.get("phrase", "") and "?" not in item.get("canonical_value", "")
        ]
        self._save_payload(payload)

    def get_phrase_map(self, mapping_type: str) -> dict[str, str]:
        return {
            item["phrase"]: item["canonical_value"]
            for item in self._load_payload()["mappings"]
            if item["mapping_type"] == mapping_type
        }

    def log_dialogue_example(
        self,
        *,
        session_id: str,
        text: str,
        extracted_conditions: dict[str, Any],
        action: str,
    ) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "text": text,
            "action": action,
            "extracted_conditions": extracted_conditions,
        }
        with self.dialogue_log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent_dialogue_examples(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.dialogue_log_path.exists():
            return []
        lines = self.dialogue_log_path.read_text(encoding="utf-8").splitlines()
        examples = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                examples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return examples

    def _load_payload(self) -> dict[str, list[dict[str, str]]]:
        if not self.mapping_path.exists():
            return {"mappings": []}
        try:
            return json.loads(self.mapping_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"mappings": []}

    def _save_payload(self, payload: dict[str, Any]) -> None:
        self.mapping_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
