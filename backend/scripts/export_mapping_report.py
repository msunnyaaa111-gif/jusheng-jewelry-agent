from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
EXPORT_DIR = DATA_DIR / "exports"
LEARNED_MAPPINGS_PATH = DATA_DIR / "learned_mappings.json"
TRAINING_LOG_PATH = DATA_DIR / "mapping_training_log.jsonl"

STOP_PHRASES = {
    "想看", "想要", "有没有", "给我", "帮我", "这个", "那个", "左右", "预算", "价格", "推荐", "一条", "一个",
    "可以", "一下", "比较", "带的", "送给", "给他", "给她", "自己", "手链", "项链", "耳环", "戒指", "手串",
}

CATEGORY_HINTS = ["链", "坠", "镯", "串", "环", "戒", "耳", "饰", "绳", "圈"]
GIFT_TARGET_HINTS = ["男", "女", "妈", "婆", "爸", "闺蜜", "姐妹", "自己", "自用", "长辈", "对象", "老公", "老婆"]
LUXURY_STYLE_HINTS = [
    "贵", "档次", "体面", "大牌", "轻奢", "高级", "气质", "优雅", "知性", "百搭", "日常", "复古", "法式", "新中式",
    "小众", "值", "划算", "超值", "性价比", "耐看", "精致",
]
MATERIAL_HINTS = ["金", "银", "玉", "翠", "珠", "宝石", "钻", "蜜蜡", "玛瑙", "檀", "朱砂", "和田玉", "翡翠"]


def load_learned_mappings() -> list[dict[str, str]]:
    if not LEARNED_MAPPINGS_PATH.exists():
        return []
    try:
        payload = json.loads(LEARNED_MAPPINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload.get("mappings", [])


def load_training_examples() -> list[dict[str, Any]]:
    if not TRAINING_LOG_PATH.exists():
        return []
    examples: list[dict[str, Any]] = []
    for line in TRAINING_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            examples.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return examples


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("\ufeff", "").replace("\u200b", "").replace("\xa0", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def known_phrases(mappings: list[dict[str, str]]) -> set[str]:
    phrases = set()
    for item in mappings:
        phrases.add(item.get("phrase", ""))
        phrases.add(item.get("canonical_value", ""))
    return {item for item in phrases if item}


def extract_candidate_ngrams(text: str) -> list[str]:
    normalized = normalize_text(text)
    chunks = re.findall(r"[\u4e00-\u9fff]{2,16}", normalized)
    candidates: list[str] = []
    for chunk in chunks:
        upper = min(6, len(chunk))
        for size in range(2, upper + 1):
            for start in range(0, len(chunk) - size + 1):
                candidate = chunk[start : start + size]
                if candidate in STOP_PHRASES:
                    continue
                candidates.append(candidate)
    return candidates


def classify_candidate_phrase(phrase: str) -> str:
    if any(token in phrase for token in CATEGORY_HINTS):
        return "category"
    if any(token in phrase for token in GIFT_TARGET_HINTS):
        return "gift_target"
    if any(token in phrase for token in MATERIAL_HINTS):
        return "material"
    if any(token in phrase for token in LUXURY_STYLE_HINTS):
        return "luxury_or_style"
    return "other"


def build_report() -> dict[str, Any]:
    mappings = load_learned_mappings()
    examples = load_training_examples()
    known = known_phrases(mappings)

    ngram_counter: Counter[str] = Counter()
    phrase_examples: dict[str, list[str]] = defaultdict(list)
    recent_examples = examples[-100:]
    for example in recent_examples:
        extracted = example.get("extracted_conditions") or {}
        if any(extracted.get(field) for field in ["category", "gift_target", "luxury_intent", "style_preferences"]):
            continue
        for candidate in extract_candidate_ngrams(example.get("text", "")):
            if candidate in known or candidate in STOP_PHRASES:
                continue
            ngram_counter[candidate] += 1
            if len(phrase_examples[candidate]) < 3 and example.get("text") not in phrase_examples[candidate]:
                phrase_examples[candidate].append(example.get("text", ""))

    candidate_phrases = [
        {
            "phrase": phrase,
            "count": count,
            "group": classify_candidate_phrase(phrase),
            "examples": phrase_examples.get(phrase, []),
        }
        for phrase, count in ngram_counter.most_common(50)
        if count >= 2
    ]

    grouped_candidates: dict[str, list[dict[str, Any]]] = {
        "category": [],
        "gift_target": [],
        "luxury_or_style": [],
        "material": [],
        "other": [],
    }
    for item in candidate_phrases:
        grouped_candidates[item["group"]].append(item)

    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "date": today,
        "stats": {
            "learned_mapping_count": len(mappings),
            "training_example_count": len(examples),
            "candidate_phrase_count": len(candidate_phrases),
        },
        "learned_mappings": mappings,
        "recent_examples": recent_examples[-20:],
        "candidate_phrases": candidate_phrases,
        "grouped_candidate_phrases": grouped_candidates,
    }


def write_outputs(report: dict[str, Any]) -> tuple[Path, Path]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    date = report["date"]
    json_path = EXPORT_DIR / f"mapping-report-{date}.json"
    md_path = EXPORT_DIR / f"mapping-report-{date}.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Mapping Report {date}",
        "",
        "## 概览",
        f"- 已生效映射数：{report['stats']['learned_mapping_count']}",
        f"- 训练样本数：{report['stats']['training_example_count']}",
        f"- 高频候选词数：{report['stats']['candidate_phrase_count']}",
        "",
        "## 已生效映射",
    ]
    if report["learned_mappings"]:
        for item in report["learned_mappings"]:
            lines.append(f"- `{item['mapping_type']}`: `{item['phrase']}` -> `{item['canonical_value']}`")
    else:
        lines.append("- 暂无")

    lines.extend(["", "## 高频候选词"])
    grouped = report.get("grouped_candidate_phrases") or {}
    group_labels = {
        "category": "品类候选",
        "gift_target": "送礼对象候选",
        "luxury_or_style": "显贵/风格候选",
        "material": "材质候选",
        "other": "其它候选",
    }
    if report["candidate_phrases"]:
        for group_key in ["category", "gift_target", "luxury_or_style", "material", "other"]:
            lines.extend(["", f"### {group_labels[group_key]}"])
            items = grouped.get(group_key) or []
            if not items:
                lines.append("- 暂无")
                continue
            for item in items:
                example_text = f"  例句：{item['examples'][0]}" if item.get("examples") else ""
                lines.append(f"- `{item['phrase']}`: {item['count']} 次{example_text}")
    else:
        lines.append("- 暂无")

    lines.extend(["", "## 最近训练样本"])
    if report["recent_examples"]:
        for item in report["recent_examples"][-10:]:
            lines.append(f"- `{item.get('text', '')}`")
    else:
        lines.append("- 暂无")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    report = build_report()
    json_path, md_path = write_outputs(report)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
