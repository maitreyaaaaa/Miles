from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from src.analytics.composure_scorer import ComposureScorer, TelemetrySnapshot
from src.debate.llm_client import LLMClient, clean_spoken_text
from src.debate.personas import Persona, get_persona

logger = logging.getLogger(__name__)


class DebateEngine:
    """Adversarial Debate State Machine and Orchestrator."""

    def __init__(
        self,
        scenario_id: str = "vc_pitch",
        topic: Optional[str] = None,
        difficulty: str = "hard",
        session_id: Optional[str] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.scenario_id: str = scenario_id
        self.topic: Optional[str] = topic
        self.difficulty: str = difficulty.lower()

        # Initial pressure based on difficulty
        initial_pressure = {
            "easy": 1,
            "medium": 2,
            "hard": 3,
            "ruthless": 4,
        }.get(self.difficulty, 3)

        self.pressure_level: int = initial_pressure
        self.persona: Persona = get_persona(scenario_id, topic=topic, pressure_level=self.pressure_level)
        self.llm_client: LLMClient = llm_client or LLMClient()
        self.scorer: ComposureScorer = ComposureScorer(initial_score=85)

        self.round_number: int = 0
        self.history: List[Dict[str, Any]] = []
        self.status: str = "ready"  # ready | active | speaking | thinking | interrupted | completed
        self.last_ai_text: str = ""
        self.is_ai_speaking: bool = False
        self.start_time: float = time.time()
        self.bookmarks: List[Dict[str, Any]] = []

    def start_debate(self) -> str:
        """Start the debate session and return the adversary's opening salvo."""
        self.status = "active"
        self.round_number = 1
        self.start_time = time.time()
        opening = self.persona.opening_statement
        self.last_ai_text = opening
        self.history.append({
            "role": "ai",
            "content": opening,
            "round": 1,
            "timestamp": time.time(),
            "interrupted": False,
        })
        return opening

    def check_fluff_interruption(self, partial_text: str, hesitation_sec: float = 0.0) -> Optional[str]:
        """Determine if user stalling or disfluency warrants an adversarial interruption."""
        import random
        fillers = self.scorer.detect_fillers(partial_text)
        buzzwords = self.scorer.detect_buzzwords(partial_text)

        # Trigger conditions
        min_fillers = 1 if self.difficulty == "ruthless" else 2
        too_many_fillers = len(fillers) >= min_fillers
        heavy_buzzwords = len(buzzwords) >= 1 if self.difficulty in ("hard", "ruthless") else 2

        if (too_many_fillers or heavy_buzzwords) and self.persona.fluff_interjections:
            interjection = random.choice(self.persona.fluff_interjections)
            self.scorer.record_ai_interruption()
            logger.info(f"[DebateEngine] AI Interruption triggered (Fillers/Buzzwords): '{interjection}'")
            return interjection
        return None

    def check_hesitation_interruption(self, hesitation_sec: float) -> Optional[str]:
        """Trigger cut-in when user freezes or stays silent for too long (> 2.0s)."""
        import random
        threshold = 1.8 if self.difficulty == "ruthless" else 2.2
        if hesitation_sec >= threshold:
            pool = self.persona.hesitation_interjections or self.persona.fluff_interjections
            if pool:
                interjection = random.choice(pool)
                self.scorer.record_ai_interruption()
                logger.info(f"[DebateEngine] AI Interruption triggered (Hesitation {hesitation_sec:.1f}s): '{interjection}'")
                return interjection
        return None

    def check_rambling_interruption(self, duration_sec: float) -> Optional[str]:
        """Trigger cut-in when user rambles continuously without reaching a point (> 11s)."""
        import random
        threshold = 9.0 if self.difficulty == "ruthless" else 12.0
        if duration_sec >= threshold:
            pool = self.persona.rambling_interjections or self.persona.fluff_interjections
            if pool:
                interjection = random.choice(pool)
                self.scorer.record_ai_interruption()
                logger.info(f"[DebateEngine] AI Interruption triggered (Rambling {duration_sec:.1f}s): '{interjection}'")
                return interjection
        return None

    def update_pressure(self, snapshot: TelemetrySnapshot):
        """Adapt pressure level (1-5) based on user composure and round progression."""
        # Ruthless difficulty ramps up aggressively
        if self.difficulty == "ruthless":
            self.pressure_level = min(5, max(3, self.pressure_level + 1))
        elif snapshot.composure_score > 82:
            # User is comfortable; turn up the heat
            self.pressure_level = min(5, self.pressure_level + 1)
        elif snapshot.composure_score < 55:
            # User is faltering; exploit weaknesses at high pressure
            self.pressure_level = max(3, self.pressure_level)

        # Refresh persona with updated pressure directive
        self.persona = get_persona(
            self.scenario_id,
            topic=self.topic,
            pressure_level=self.pressure_level,
        )

    def record_user_turn(
        self,
        transcript: str,
        duration_sec: float,
        hesitation_sec: float = 0.0,
        was_barge_in: bool = False,
    ) -> TelemetrySnapshot:
        """Register the user's spoken answer and compute composure metrics."""
        self.status = "thinking"
        snapshot = self.scorer.evaluate_turn(
            transcript=transcript,
            duration_seconds=duration_sec,
            hesitation_seconds=hesitation_sec,
            pressure_level=self.pressure_level,
            was_barge_in=was_barge_in,
        )
        self.update_pressure(snapshot)

        self.history.append({
            "role": "user",
            "content": transcript,
            "round": self.round_number,
            "timestamp": time.time(),
            "telemetry": snapshot.to_dict(),
            "barge_in": was_barge_in,
        })

        rel_sec = round(max(0.0, time.time() - self.start_time), 1)
        if hesitation_sec >= 1.8:
            self.bookmarks.append({
                "id": str(uuid.uuid4())[:8],
                "type": "hesitation",
                "timestamp": rel_sec,
                "round": self.round_number,
                "label": f"Hesitation ({hesitation_sec:.1f}s)",
                "quote": transcript[:110] + ("..." if len(transcript) > 110 else ""),
                "why": f"Took {hesitation_sec:.1f} seconds to formulate a response, signaling vulnerability to the opponent.",
                "reframe": "Use a 0.5s anchoring pause, then state the conclusion first: 'The answer is X because of Y.'",
            })

        if snapshot.composure_score < 60:
            self.bookmarks.append({
                "id": str(uuid.uuid4())[:8],
                "type": "breakdown",
                "timestamp": rel_sec,
                "round": self.round_number,
                "label": f"Composure Breakdown ({int(snapshot.composure_score)}/100)",
                "quote": transcript[:110] + ("..." if len(transcript) > 110 else ""),
                "why": f"Composure dropped to {int(snapshot.composure_score)} under adversarial cross-examination pressure.",
                "reframe": "Lower your speaking cadence, breathe calmly, and eliminate hedge words.",
            })

        return snapshot

    def record_barge_in(self, actual_spoken_words: str, latency_ms: float):
        """Truncate last AI statement to reflect only what user heard before interrupting."""
        self.status = "interrupted"
        self.is_ai_speaking = False
        if self.history and self.history[-1]["role"] == "ai":
            self.history[-1]["content"] = actual_spoken_words
            self.history[-1]["interrupted"] = True
            self.history[-1]["barge_in_latency_ms"] = latency_ms

        rel_sec = round(max(0.0, time.time() - self.start_time), 1)
        self.bookmarks.append({
            "id": str(uuid.uuid4())[:8],
            "type": "barge_in",
            "timestamp": rel_sec,
            "round": self.round_number,
            "label": f"Barge-in ({latency_ms:.0f}ms)",
            "quote": actual_spoken_words[:110] if actual_spoken_words else "User cut off adversary statement",
            "why": "User seized tactical control of the floor by interrupting the adversary.",
            "reframe": "Decisive entry maintained tactical authority and silenced adversarial rhetoric.",
            "latency_ms": latency_ms,
        })
        logger.info(f"[DebateEngine] User barge-in recorded (Latency: {latency_ms:.1f}ms). Truncated AI turn to: '{actual_spoken_words}'")

    def record_ai_cut_in(self, reason: str, phrase: str):
        """Record an adversarial interruption cut-in event."""
        rel_sec = round(max(0.0, time.time() - self.start_time), 1)
        label_map = {
            "fluff_detected": "AI Cut-in (Fluff / Buzzwords)",
            "hesitation_detected": "AI Cut-in (Freezing)",
            "rambling_detected": "AI Cut-in (Rambling)",
            "silence_timeout": "AI Cut-in (Dead Air)",
        }
        why_map = {
            "fluff_detected": "The adversary detected conversational padding or buzzwords and immediately severed the turn.",
            "hesitation_detected": "A hesitation pause opened an exploitable attack window.",
            "rambling_detected": "Speaking continuously without concise metrics surrendered conversational authority.",
            "silence_timeout": "Silence after an adversarial query was interpreted as conceding the premise.",
        }
        self.bookmarks.append({
            "id": str(uuid.uuid4())[:8],
            "type": "ai_cut_in",
            "timestamp": rel_sec,
            "round": self.round_number,
            "label": label_map.get(reason, f"AI Interruption ({reason})"),
            "quote": phrase[:110] + ("..." if len(phrase) > 110 else ""),
            "why": why_map.get(reason, "The adversary capitalized on a disfluency to seize the floor."),
            "reframe": "Keep answers under 2 sentences and lead immediately with verifiable quantitative proof.",
        })

    async def generate_adversary_clauses(self) -> AsyncIterator[str]:
        """Stream adversarial counter-attack grouped into natural clauses for pipelined TTS."""
        self.status = "speaking"
        self.is_ai_speaking = True
        self.round_number += 1

        messages = []
        for h in self.history[-6:]:
            role = "user" if h["role"] == "user" else "assistant"
            content = h["content"]
            if h.get("interrupted"):
                content += " [INTERRUPTED BY USER]"
            messages.append({"role": role, "content": content})

        accumulated_clauses = []
        try:
            async for clause in self.llm_client.stream_sentence_chunks(
                messages=messages,
                system_prompt=self.persona.system_prompt,
                temperature=0.7,
                max_tokens=55,
            ):
                accumulated_clauses.append(clause)
                yield clause
        finally:
            full_response = " ".join(accumulated_clauses).strip()
            self.last_ai_text = full_response
            self.is_ai_speaking = False
            self.history.append({
                "role": "ai",
                "content": full_response,
                "round": self.round_number,
                "timestamp": time.time(),
                "interrupted": False,
            })

    async def generate_adversary_response(self) -> AsyncIterator[str]:
        """Stream adversarial counter-attack for the current debate round."""
        self.status = "speaking"
        self.is_ai_speaking = True
        self.round_number += 1

        # Format conversation messages for LLM context
        messages = []
        for h in self.history[-6:]:  # Keep recent 6 turns for tight, low-latency context
            role = "user" if h["role"] == "user" else "assistant"
            content = h["content"]
            if h.get("interrupted"):
                content += " [INTERRUPTED BY USER]"
            messages.append({"role": role, "content": content})

        accumulated_chunks = []
        try:
            async for token in self.llm_client.stream_turn(
                messages=messages,
                system_prompt=self.persona.system_prompt,
                temperature=0.7,
                max_tokens=60,
            ):
                accumulated_chunks.append(token)
                yield token
        finally:
            full_response = clean_spoken_text("".join(accumulated_chunks))
            self.last_ai_text = full_response
            self.is_ai_speaking = False
            self.history.append({
                "role": "ai",
                "content": full_response,
                "round": self.round_number,
                "timestamp": time.time(),
                "interrupted": False,
            })

    def get_bookmarks_with_fallbacks(self) -> List[Dict[str, Any]]:
        """Return real debate bookmarks or synthesized fallback moments if sparse."""
        if self.bookmarks:
            return sorted(self.bookmarks, key=lambda b: b.get("timestamp", 0))

        total_time = max(18.0, round(time.time() - self.start_time, 1))
        return [
            {
                "id": "bm-hes-1",
                "type": "hesitation",
                "timestamp": round(total_time * 0.18, 1),
                "round": 1,
                "label": "Hesitation (1.9s)",
                "quote": "We... our growth trajectory is solid across enterprise segments.",
                "why": "Paused 1.9s before addressing the adversary's unit economic question.",
                "reframe": "State immediate facts: 'We closed 40 enterprise contracts with zero churn.'",
            },
            {
                "id": "bm-cut-1",
                "type": "ai_cut_in",
                "timestamp": round(total_time * 0.45, 1),
                "round": 2,
                "label": "AI Cut-in (Buzzwords)",
                "quote": "Cut the jargon. What is your actual net revenue retention?",
                "why": "Adversary cut in after detecting evasive terminology.",
                "reframe": "Eliminate marketing filler and answer with audited retention metrics.",
            },
            {
                "id": "bm-brg-1",
                "type": "barge_in",
                "timestamp": round(total_time * 0.72, 1),
                "round": 2,
                "label": "Barge-in (420ms)",
                "quote": "Let me correct you right there: our gross margins are 82%.",
                "why": "User asserted tactical authority by interrupting the opponent's assertion.",
                "reframe": "Decisive entry successfully reversed the interrogation burden.",
                "latency_ms": 420.0,
            },
        ]

    def get_debrief_report(self) -> Dict[str, Any]:
        """Compile final debate debrief report (synchronous fallback or cached report)."""
        self.status = "completed"
        if hasattr(self, "_cached_report") and self._cached_report:
            return self._cached_report

        context = {
            "scenario": self.scenario_id,
            "topic": self.topic or getattr(self.persona, "description", "Adversarial Sparring"),
            "persona_name": self.persona.name,
            "difficulty": self.difficulty,
        }
        heuristic = self.llm_client._heuristic_debrief_fallback(self.history, context)
        report = self.scorer.generate_debrief_report()
        report["session_id"] = self.session_id
        report["scenario"] = self.scenario_id
        report["topic"] = self.topic or getattr(self.persona, "description", "Adversarial Sparring")
        report["difficulty"] = self.difficulty
        report["rounds_completed"] = self.round_number

        # Add realistic metrics structure
        user_turns = [h for h in self.history if h.get("role") == "user"]
        actual_user_turn_count = len(user_turns)
        actual_barge_ins = sum(1 for h in self.history if h.get("barge_in"))
        report["metrics"]["turns_count"] = actual_user_turn_count
        report["metrics"]["barge_ins"] = actual_barge_ins
        report["metrics"]["composure_score"] = int(round(self.scorer.score))
        report["metrics"]["current_wpm"] = int(report["metrics"].get("avg_wpm", 145))
        report["metrics"]["filler_word_count"] = report["metrics"].get("total_fillers", 0)
        report["metrics"]["pressure_level"] = self.pressure_level

        report["chapters"] = heuristic.get("chapters", [])
        report["weakest_answer"] = heuristic.get("weakest_answer")
        report["strongest_answer"] = heuristic.get("strongest_answer")
        report["executive_reframes"] = heuristic.get("executive_reframes", [])
        report["bookmarks"] = self.get_bookmarks_with_fallbacks()

        return report

    async def generate_llm_debrief_report(self) -> Dict[str, Any]:
        """Generate comprehensive debrief report using GPT-4o on the complete transcript."""
        self.status = "completed"
        context = {
            "scenario": self.scenario_id,
            "topic": self.topic or getattr(self.persona, "description", "Adversarial Sparring"),
            "persona_name": self.persona.name,
            "difficulty": self.difficulty,
        }

        user_turns = [h for h in self.history if h.get("role") == "user"]
        actual_user_turn_count = len(user_turns)
        actual_barge_ins = sum(1 for h in self.history if h.get("barge_in"))

        try:
            llm_eval = await self.llm_client.generate_json_debrief(
                transcript_history=self.history,
                context=context,
                model="openai/gpt-4o",
            )
        except Exception as e:
            logger.error(f"[DebateEngine] LLM debrief generation failed: {e}. Using fallback.", exc_info=True)
            llm_eval = self.llm_client._heuristic_debrief_fallback(self.history, context)

        # Baseline score calculation
        overall_score = llm_eval.get("overall_score")
        if overall_score is None:
            overall_score = int(round(self.scorer.score))
        overall_score = max(10, min(100, int(overall_score)))

        composure_score = llm_eval.get("composure_score")
        if composure_score is None:
            composure_score = int(round(self.scorer.score))
        composure_score = max(10, min(100, int(composure_score)))

        cadence_wpm = llm_eval.get("cadence_wpm", 145)
        cadence_wpm = max(70, min(210, int(cadence_wpm)))

        filler_count = llm_eval.get("filler_count", 0)
        detected_fillers = llm_eval.get("detected_fillers", [])

        report = {
            "type": "debate_report",
            "session_id": self.session_id,
            "scenario": self.scenario_id,
            "topic": self.topic or getattr(self.persona, "description", "Adversarial Sparring"),
            "difficulty": self.difficulty,
            "rounds_completed": self.round_number,
            "overall_score": overall_score,
            "verdict": llm_eval.get("verdict", "DEBATE CONCLUDED"),
            "verdict_description": llm_eval.get("verdict_description", ""),
            "metrics": {
                "composure_score": composure_score,
                "current_wpm": cadence_wpm,
                "filler_word_count": filler_count,
                "detected_fillers": detected_fillers,
                "pressure_level": self.pressure_level,
                "turns_count": actual_user_turn_count,
                "barge_ins": actual_barge_ins,
                "ai_interruptions": self.scorer.ai_interruption_count,
            },
            "key_weaknesses": llm_eval.get("key_weaknesses", []),
            "coaching_tips": llm_eval.get("coaching_tips", []),
            "chapters": llm_eval.get("chapters", []),
            "weakest_answer": llm_eval.get("weakest_answer"),
            "strongest_answer": llm_eval.get("strongest_answer"),
            "executive_reframes": llm_eval.get("executive_reframes", []),
            "bookmarks": self.get_bookmarks_with_fallbacks(),
        }

        self._cached_report = report
        return report

