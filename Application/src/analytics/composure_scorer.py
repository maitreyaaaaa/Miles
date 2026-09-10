from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

FILLER_WORDS: Set[str] = {
    "um", "uh", "umm", "uhh", "ah", "er", "hmm", "like", "basically",
    "actually", "literally", "sort of", "kind of", "you know", "i mean",
    "sorta", "kinda",
}

BUZZWORDS: Set[str] = {
    "synergy", "synergies", "paradigm", "disrupt", "disruptive",
    "holistic", "game-changer", "revolutionary", "bleeding-edge",
    "next-gen", "seamless", "frictionless", "wheelhouse",
}


@dataclass
class TelemetrySnapshot:
    composure_score: int
    current_wpm: float
    filler_word_count: int
    recent_fillers: List[str]
    hesitation_seconds: float
    pressure_level: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "composure_telemetry",
            "composure_score": self.composure_score,
            "current_wpm": round(self.current_wpm, 1),
            "filler_word_count": self.filler_word_count,
            "recent_fillers": self.recent_fillers,
            "hesitation_seconds": round(self.hesitation_seconds, 2),
            "pressure_level": self.pressure_level,
        }


class ComposureScorer:
    """Real-time composure & speech cadence intelligence engine for Miles."""

    def __init__(self, initial_score: int = 85):
        self.score: float = float(initial_score)
        self.total_words: int = 0
        self.total_duration_sec: float = 0.0
        self.filler_words_detected: List[str] = []
        self.hesitation_events: List[float] = []
        self.user_barge_in_count: int = 0
        self.ai_interruption_count: int = 0
        self.history: List[TelemetrySnapshot] = []
        self.turn_weaknesses: List[str] = []

    def detect_fillers(self, text: str) -> List[str]:
        """Identify conversational fillers in transcript text."""
        normalized = text.lower()
        found: List[str] = []

        # Multi-word fillers
        for mw in ["you know", "sort of", "kind of", "i mean"]:
            if mw in normalized:
                count = normalized.count(mw)
                found.extend([mw] * count)
                normalized = normalized.replace(mw, " ")

        # Filter out syntactic valid usages of "like" (verbs, prepositions, similes)
        # e.g., "would like", "like to", "look like", "looks like", "feels like"
        normalized = re.sub(r"\b(would|could|should|might|i'd)\s+like\b", " ", normalized)
        normalized = re.sub(r"\blike\s+to\b", " ", normalized)
        normalized = re.sub(r"\b(look|looks|looked|feel|feels|felt|seem|seems|seemed|sound|sounds)\s+like\b", " ", normalized)

        # Single word fillers
        tokens = re.findall(r"\b[a-zA-Z']+\b", normalized)
        for tok in tokens:
            if tok in FILLER_WORDS:
                found.append(tok)

        return found

    def detect_buzzwords(self, text: str) -> List[str]:
        """Detect evasion buzzwords that prompt adversarial interjection."""
        tokens = set(re.findall(r"\b[a-zA-Z-]+\b", text.lower()))
        return list(tokens.intersection(BUZZWORDS))

    def evaluate_turn(
        self,
        transcript: str,
        duration_seconds: float,
        hesitation_seconds: float = 0.0,
        pressure_level: int = 3,
        was_barge_in: bool = False,
    ) -> TelemetrySnapshot:
        """Score a speech segment and produce real-time telemetry."""
        words = re.findall(r"\b\w+\b", transcript)
        word_count = len(words)
        self.total_words += word_count

        # Human conversational rate is ~130-180 WPM. Guard against unrealistic duration glitches.
        min_physical_duration = word_count / (220.0 / 60.0) if word_count > 0 else 0.5
        effective_duration = max(duration_seconds, min_physical_duration, 0.8)
        self.total_duration_sec += effective_duration

        # Cadence (Words Per Minute) clamped to human norms
        raw_wpm = (word_count / effective_duration) * 60.0
        wpm = max(70.0, min(220.0, raw_wpm)) if word_count > 2 else 135.0

        # Fillers
        fillers = self.detect_fillers(transcript)
        self.filler_words_detected.extend(fillers)

        # Hesitations
        if hesitation_seconds > 0:
            self.hesitation_events.append(hesitation_seconds)

        if was_barge_in:
            self.user_barge_in_count += 1

        # Dynamic score calculation
        delta = 0.0

        # 1. Fillers penalty
        filler_penalty = len(fillers) * 3.5
        delta -= filler_penalty
        if len(fillers) >= 2:
            self.turn_weaknesses.append(f"Clustered filler words: '{', '.join(fillers)}'")

        # 2. Hesitation penalty
        if hesitation_seconds > 2.0:
            delta -= (hesitation_seconds - 1.5) * 4.0
            self.turn_weaknesses.append(f"Excessive verbal pause ({hesitation_seconds:.1f}s)")

        # 3. WPM Stability
        if 130 <= wpm <= 170:
            delta += 2.0  # Confident conversational speed
        elif wpm > 210:
            delta -= 4.0  # Rushed / panicked
            self.turn_weaknesses.append(f"Panicked speech cadence ({int(wpm)} WPM)")
        elif wpm < 85 and word_count > 3:
            delta -= 3.5  # Dragging / halting
            self.turn_weaknesses.append(f"Halting speech delivery ({int(wpm)} WPM)")

        # 4. Conciseness reward
        if 8 <= word_count <= 28 and len(fillers) == 0:
            delta += 3.5  # Crisp, punchy defense

        # 5. Active counter-assertion reward
        if was_barge_in:
            delta += 4.0  # High confidence assertiveness

        # Apply delta with pressure multiplier
        pressure_multiplier = 0.8 + (pressure_level * 0.1)
        self.score += delta * pressure_multiplier

        # Clamp between 10 and 100
        self.score = max(10.0, min(100.0, self.score))

        snapshot = TelemetrySnapshot(
            composure_score=int(round(self.score)),
            current_wpm=wpm,
            filler_word_count=len(self.filler_words_detected),
            recent_fillers=fillers[-4:],
            hesitation_seconds=hesitation_seconds,
            pressure_level=pressure_level,
        )
        self.history.append(snapshot)
        return snapshot

    def record_ai_interruption(self):
        """Record an adversarial AI cut-off due to fluff or hesitation."""
        self.ai_interruption_count += 1
        self.score = max(10.0, self.score - 6.0)

    def generate_debrief_report(self) -> Dict[str, Any]:
        """Compile comprehensive post-debate assessment."""
        final_score = int(round(self.score)) if self.history else 75
        raw_avg_wpm = (self.total_words / max(self.total_duration_sec, 1.0)) * 60.0
        avg_wpm = max(75.0, min(210.0, raw_avg_wpm)) if self.total_words > 0 else 140.0

        if final_score >= 82:
            verdict = "MASTER NEGOTIATOR"
            verdict_desc = "Unshakable verbal composure under intense adversarial grilling."
        elif final_score >= 68:
            verdict = "CHALLENGE SURVIVED"
            verdict_desc = "Defended positions effectively with minor hesitation under pressure."
        elif final_score >= 52:
            verdict = "STRUGGLED UNDER PRESSURE"
            verdict_desc = "Adversary successfully exposed hesitation and defensive instability."
        else:
            verdict = "DESTROYED BY ADVERSARY"
            verdict_desc = "Crumbled under cross-examination with excessive disfluencies and evasions."

        # Filter unique weaknesses
        unique_weaknesses = list(dict.fromkeys(self.turn_weaknesses))[:4]
        if not unique_weaknesses:
            unique_weaknesses = ["No major disfluencies detected during active rounds."]

        # Actionable coaching tips
        coaching_tips = []
        if len(self.filler_words_detected) > 3:
            coaching_tips.append("Replace vocal fillers ('um', 'like') with clean, deliberate silence.")
        if any(h > 2.0 for h in self.hesitation_events):
            coaching_tips.append("Lead with your core conclusion immediately rather than stalling to calculate.")
        if avg_wpm > 190:
            coaching_tips.append("Slow your speech cadence down to ~150 WPM to project commanding authority.")
        elif avg_wpm < 100:
            coaching_tips.append("Increase speech momentum; sluggish replies invite adversarial interruptions.")
        if not coaching_tips:
            coaching_tips.append("Maintain your concise, punchy cadence and crisp numerical assertions.")

        return {
            "type": "debate_report",
            "overall_score": final_score,
            "verdict": verdict,
            "verdict_description": verdict_desc,
            "metrics": {
                "avg_wpm": round(avg_wpm, 1),
                "total_words": self.total_words,
                "total_fillers": len(self.filler_words_detected),
                "filler_breakdown": {f: self.filler_words_detected.count(f) for f in set(self.filler_words_detected)},
                "barge_ins": self.user_barge_in_count,
                "ai_interruptions": self.ai_interruption_count,
            },
            "key_weaknesses": unique_weaknesses,
            "coaching_tips": coaching_tips,
        }
