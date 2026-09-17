from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RhetoricalTactic:
    id: str
    name: str
    description: str
    hint_phrase: str
    counter_strategy: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Predefined rhetorical tactics commonly deployed by adversarial interviewers
TACTICS: List[RhetoricalTactic] = [
    RhetoricalTactic(
        id="false_dilemma",
        name="False Dilemma",
        description="Forcing an artificial either/or choice between two undesirable extremes.",
        hint_phrase="Challenge false dichotomy",
        counter_strategy="Reject the binary framing and introduce the third viable operational path.",
    ),
    RhetoricalTactic(
        id="anchoring_trap",
        name="Anchoring Trap",
        description="Fixating aggressively on a low baseline valuation, budget cap, or legacy standard.",
        hint_phrase="Reset baseline to ROI",
        counter_strategy="Refuse to negotiate from their anchor; ground the conversation in quantifiable forward value.",
    ),
    RhetoricalTactic(
        id="shifting_burden",
        name="Shifting Burden of Proof",
        description="Demanding you prove a negative or defend an unprovable hypothetical catastrophe.",
        hint_phrase="Return burden to data",
        counter_strategy="Anchor firmly to historical cohort data rather than speculating on hypothetical worst cases.",
    ),
    RhetoricalTactic(
        id="leading_trap",
        name="Leading Interrogation",
        description="Framing the question with an embedded admission of guilt or vulnerability.",
        hint_phrase="Reject embedded premise",
        counter_strategy="Explicitly reject the premise of the question before stating your verified facts.",
    ),
    RhetoricalTactic(
        id="vagueness_pressure",
        name="Numeric Extraction Pressure",
        description="Dismissing all qualitative explanation to corner you into hard, unforgiving numbers.",
        hint_phrase="State exact metric first",
        counter_strategy="Give the single crisp number immediately, then qualify in one short sentence.",
    ),
    RhetoricalTactic(
        id="defensiveness_bait",
        name="Emotional Agitation Bait",
        description="Attacking competence or composure to provoke an emotional, rambling over-explanation.",
        hint_phrase="Pause, breathe, stay clinical",
        counter_strategy="Lower vocal pitch, eliminate filler, and answer with clinical detachment.",
    ),
]


class TacticDetector:
    """Detects rhetorical trap tactics deployed in adversary utterances and suggests 3-word recovery hints."""

    def __init__(self):
        self._patterns = [
            ("false_dilemma", [
                r"\beither\b.*\bor\b",
                r"which is it\b",
                r"pick one\b",
                r"die or pivot\b",
            ]),
            ("anchoring_trap", [
                r"\bband ceiling\b",
                r"\bstandard cap\b",
                r"\bnever pay more than\b",
                r"\bvaluation is capped\b",
                r"\bmarket rate is\b",
            ]),
            ("shifting_burden", [
                r"\bprove to me that\b",
                r"\bhow do you know.*\bwon't\b",
                r"\bguarantee that\b",
                r"\bconvince me\b",
            ]),
            ("leading_trap", [
                r"\bisn't it true that\b",
                r"\badmit that\b",
                r"\bwouldn't you agree\b",
                r"\bdoesn't that mean\b",
                r"\bwhy did you fail\b",
            ]),
            ("vagueness_pressure", [
                r"\bcut the (?:fluff|buzzwords|jargon)\b",
                r"\bwhat is your actual\b",
                r"\bwhat is the hard number\b",
                r"\bexact (?:cac|retention|churn|margin|number)\b",
                r"\byes or no\b",
            ]),
            ("defensiveness_bait", [
                r"\byou(?:'re| are) dodging\b",
                r"\byou(?:'re| are) stalling\b",
                r"\bdon't freeze up\b",
                r"\bwhy the hesitation\b",
                r"\blost your train of thought\b",
            ]),
        ]

    def detect_tactic(self, ai_text: str) -> RhetoricalTactic:
        """Analyze adversary text and classify the active rhetorical trap."""
        lowered = ai_text.lower()

        for tactic_id, patterns in self._patterns:
            for pat in patterns:
                if re.search(pat, lowered):
                    for t in TACTICS:
                        if t.id == tactic_id:
                            return t

        # Default fallback tactic
        return TACTICS[4]  # vagueness_pressure
