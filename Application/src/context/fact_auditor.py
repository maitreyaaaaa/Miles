from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.context.analyzer import ContextDossier, NumericMetric

logger = logging.getLogger(__name__)

# Spoken number word to digit map
NUMBER_WORDS: Dict[str, float] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000,
}


@dataclass
class FactCheckItem:
    metric_name: str
    ground_truth_raw: str
    ground_truth_val: float
    user_stated_raw: str
    user_stated_val: float
    is_accurate: bool
    discrepancy_note: str
    rectification_salvo: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FactCheckResult:
    has_audit_event: bool
    verified_items: List[FactCheckItem] = field(default_factory=list)
    discrepancies: List[FactCheckItem] = field(default_factory=list)
    immediate_rectification: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_audit_event": self.has_audit_event,
            "verified_items": [v.to_dict() for v in self.verified_items],
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "immediate_rectification": self.immediate_rectification,
        }


def _extract_numeric_mentions(text: str) -> List[Tuple[str, float]]:
    """Extract numeric values and their context snippets from user text."""
    mentions: List[Tuple[str, float]] = []
    lowered = text.lower()

    # 1. Regex for standard numbers with currency/symbols: $45, 12%, 1.5M, 200k, 14
    regex_num = re.findall(r"([\$€£]?\s*[0-9]+(?:\.[0-9]+)?\s*(?:[kKmMbB]|percent|%|dollars)?)", text)
    for raw in regex_num:
        clean = raw.strip()
        if not clean:
            continue
        val = 0.0
        multiplier = 1.0
        u = clean.upper()
        if "B" in u or "BILLION" in u:
            multiplier = 1_000_000_000.0
        elif "M" in u or "MILLION" in u:
            multiplier = 1_000_000.0
        elif "K" in u or "THOUSAND" in u:
            multiplier = 1_000.0

        digits = re.findall(r"[0-9]+(?:\.[0-9]+)?", clean)
        if digits:
            try:
                val = float(digits[0]) * multiplier
                mentions.append((clean, val))
            except ValueError:
                pass

    # 2. Extract common spoken phrases like "forty five dollars", "two million", "ten percent"
    spoken_patterns = [
        (r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)\s+(hundred|thousand|million|billion)?\s*(dollars|percent)?\b", 1),
    ]
    for pattern, _ in spoken_patterns:
        for m in re.finditer(pattern, lowered):
            full_match = m.group(0)
            words = full_match.split()
            base = NUMBER_WORDS.get(words[0], 0)
            mul = 1.0
            if len(words) > 1:
                if words[1] in ("hundred", "thousand", "million", "billion"):
                    mul = NUMBER_WORDS.get(words[1], 1.0)
            total = base * mul
            if total > 0 and not any(abs(m[1] - total) < 0.001 for m in mentions):
                mentions.append((full_match, total))

    return mentions


class FactAuditor:
    """Verifies user spoken answers in real-time against an uploaded Context Dossier."""

    def __init__(self, dossier: Optional[ContextDossier] = None):
        self.dossier: Optional[ContextDossier] = dossier
        self.verified_history: List[FactCheckItem] = []
        self.discrepancy_history: List[FactCheckItem] = []
        self._metric_keywords: Dict[str, List[NumericMetric]] = {}
        if self.dossier:
            self._index_metrics()

    def set_dossier(self, dossier: ContextDossier):
        self.dossier = dossier
        self._index_metrics()

    def _index_metrics(self):
        """Index metrics by keywords for fast fuzzy matching."""
        self._metric_keywords.clear()
        if not self.dossier:
            return

        for m in self.dossier.numeric_metrics:
            # Extract keywords from metric name and context
            combined = f"{m.name} {m.category} {m.context}".lower()
            tokens = set(re.findall(r"\b[a-z0-9-]{3,}\b", combined))
            for tok in tokens:
                if tok not in self._metric_keywords:
                    self._metric_keywords[tok] = []
                self._metric_keywords[tok].append(m)

    def audit_user_turn(self, transcript: str) -> FactCheckResult:
        """Analyze finalized user statement and detect matches or discrepancies."""
        if not self.dossier or not self.dossier.numeric_metrics:
            return FactCheckResult(has_audit_event=False)

        lowered = transcript.lower()
        mentions = _extract_numeric_mentions(transcript)
        if not mentions:
            return FactCheckResult(has_audit_event=False)

        verified: List[FactCheckItem] = []
        discrepancies: List[FactCheckItem] = []

        # Find which metrics are relevant to this user statement
        matched_metrics: List[NumericMetric] = []
        tokens = set(re.findall(r"\b[a-z0-9-]{3,}\b", lowered))
        candidate_scores: Dict[str, Tuple[int, NumericMetric]] = {}

        for tok in tokens:
            if tok in self._metric_keywords:
                for m in self._metric_keywords[tok]:
                    key = m.name
                    curr_score = candidate_scores.get(key, (0, m))[0]
                    candidate_scores[key] = (curr_score + 1, m)

        # Sort by relevance score
        sorted_candidates = sorted(candidate_scores.values(), key=lambda x: x[0], reverse=True)
        relevant_metrics = [m for score, m in sorted_candidates if score >= 1]

        # If no specific keyword matched, test against high-importance metrics
        if not relevant_metrics and len(mentions) == 1:
            # Check if value is very close to any known metric
            for m in self.dossier.numeric_metrics:
                for mention_str, mention_val in mentions:
                    if m.numeric_value > 0 and abs(mention_val - m.numeric_value) / m.numeric_value < 0.15:
                        relevant_metrics.append(m)
                        break

        # Compare mentions against relevant metrics
        for metric in relevant_metrics[:3]:
            ground_val = metric.numeric_value
            if ground_val <= 0:
                continue

            for mention_str, mention_val in mentions:
                if mention_val <= 0:
                    continue

                # Check ratio
                ratio = mention_val / ground_val if ground_val > 0 else 1.0
                diff_pct = abs(mention_val - ground_val) / ground_val

                # Case A: Accurate (within 15% tolerance)
                if diff_pct <= 0.15:
                    item = FactCheckItem(
                        metric_name=metric.name,
                        ground_truth_raw=metric.raw_value,
                        ground_truth_val=ground_val,
                        user_stated_raw=mention_str,
                        user_stated_val=mention_val,
                        is_accurate=True,
                        discrepancy_note=f"Accurately cited {metric.name} ({metric.raw_value}).",
                        rectification_salvo="",
                    )
                    verified.append(item)
                    self.verified_history.append(item)
                    break

                # Case B: Significant Discrepancy / Bluffed Number (> 25% difference)
                elif diff_pct > 0.25:
                    # Construct immediate sharp adversarial rectification salvo
                    if mention_val > ground_val:
                        salvo = f"Hold on. Your document states {metric.name} is {metric.raw_value}, but you just claimed {mention_str}. Why are you inflating your numbers?"
                    else:
                        salvo = f"Wait right there. You claimed {mention_str}, but your uploaded document explicitly records {metric.raw_value} for {metric.name}. Which number is the truth?"

                    item = FactCheckItem(
                        metric_name=metric.name,
                        ground_truth_raw=metric.raw_value,
                        ground_truth_val=ground_val,
                        user_stated_raw=mention_str,
                        user_stated_val=mention_val,
                        is_accurate=False,
                        discrepancy_note=f"Discrepancy on {metric.name}: Document={metric.raw_value}, User Spoke={mention_str}.",
                        rectification_salvo=salvo,
                    )
                    discrepancies.append(item)
                    self.discrepancy_history.append(item)
                    break

        has_event = bool(verified or discrepancies)
        salvo = discrepancies[0].rectification_salvo if discrepancies else None

        return FactCheckResult(
            has_audit_event=has_event,
            verified_items=verified,
            discrepancies=discrepancies,
            immediate_rectification=salvo,
        )

    def get_audit_summary(self) -> Dict[str, Any]:
        """Compile overall ground-truth verification audit for post-debate report."""
        total = len(self.verified_history) + len(self.discrepancy_history)
        if total == 0:
            score = 100
        else:
            score = int(round((len(self.verified_history) / total) * 100))

        return {
            "has_context": bool(self.dossier),
            "document_title": self.dossier.title if self.dossier else "None",
            "document_type": self.dossier.doc_type if self.dossier else "None",
            "factual_accuracy_score": score,
            "total_audited_metrics": total,
            "verified_count": len(self.verified_history),
            "discrepancy_count": len(self.discrepancy_history),
            "verified_metrics": [v.to_dict() for v in self.verified_history],
            "discrepancies": [d.to_dict() for d in self.discrepancy_history],
            "all_ground_truth_metrics": [
                m.to_dict() if hasattr(m, "to_dict") else m
                for m in (self.dossier.numeric_metrics if self.dossier else [])
            ],
        }
