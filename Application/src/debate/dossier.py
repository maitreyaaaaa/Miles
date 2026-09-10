from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from src.debate.personas import detect_topic_polarity, infer_contrarian_thesis

logger = logging.getLogger(__name__)

DIFFICULTY_PROFILES: Dict[str, Dict[str, Any]] = {
    "easy": {
        "hesitation_threshold_sec": 3.0,
        "rambling_threshold_sec": 14.0,
        "filler_tolerance": 3,
        "adversarial_intensity": 2,
    },
    "medium": {
        "hesitation_threshold_sec": 2.3,
        "rambling_threshold_sec": 11.0,
        "filler_tolerance": 2,
        "adversarial_intensity": 3,
    },
    "hard": {
        "hesitation_threshold_sec": 2.0,
        "rambling_threshold_sec": 10.0,
        "filler_tolerance": 1,
        "adversarial_intensity": 4,
    },
    "ruthless": {
        "hesitation_threshold_sec": 1.8,
        "rambling_threshold_sec": 9.0,
        "filler_tolerance": 1,
        "adversarial_intensity": 5,
    },
}

DEFAULT_RUBRIC: Dict[str, float] = {
    "evidence_weight": 0.35,
    "cadence_weight": 0.25,
    "composure_weight": 0.25,
    "brevity_weight": 0.15,
}

CURATED_VECTORS: Dict[str, Dict[str, Any]] = {
    "remote work": {
        "vectors": [
            {"category": "Mentorship & Culture", "vector": "Tacit knowledge transfer and junior developer skill degradation without physical osmosis."},
            {"category": "Innovation Velocity", "vector": "Loss of serendipitous problem-solving and spontaneous architectural brainstorms."},
            {"category": "Mercenary Attrition", "vector": "Erosion of organizational loyalty leading to 3x higher turnover and moonlighting."},
            {"category": "Security & IP", "vector": "Client data exfiltration vulnerabilities and unmonitored local network hygiene."},
            {"category": "Operational Overhead", "vector": "Meeting sprawl and asynchronous paralysis replacing decisive five-minute alignment."},
        ],
        "traps": [
            "Name three senior architects at your firm who learned system design strictly via async Slack threads.",
            "If remote productivity is genuinely superior, why did every major hyperscaler mandate return-to-office?",
            "When a Tier-1 production incident strikes, does async chat resolve it faster than an on-site war room?",
        ],
    },
    "ai": {
        "vectors": [
            {"category": "Hallucination Risk", "vector": "Statistical confabulation posing catastrophic liability in mission-critical deployments."},
            {"category": "Unit Economics", "vector": "Skyrocketing inference compute costs eliminating software gross margin advantages."},
            {"category": "Data Poisoning & IP", "vector": "Uncontrolled copyright exposure and model collapse from recursive synthetic training."},
            {"category": "Commoditization", "vector": "Rapid open-source distillation wiping out private proprietary moats within 90 days."},
            {"category": "Regulatory Headwinds", "vector": "Upcoming EU AI Act and state-level liability frameworks restricting deployment velocity."},
        ],
        "traps": [
            "What is your gross margin once you factor in dedicated inference GPUs and token pricing?",
            "How do you legally indemnify your enterprise buyers against training data copyright litigation?",
            "If an open weights model matches your performance next month, what keeps your customers from churning?",
        ],
    },
}


def generate_fallback_dossier(
    topic: str,
    difficulty: str = "hard",
    persona_tone: str = "calm_ruthless",
) -> Dict[str, Any]:
    """Compile structured 5-vector battle dossier using heuristic intelligence."""
    clean_topic = topic.strip()
    normalized = clean_topic.lower()
    thesis = infer_contrarian_thesis(clean_topic)
    polarity = detect_topic_polarity(clean_topic)

    # Check curated vector catalog
    matched = None
    for key, data in CURATED_VECTORS.items():
        if key in normalized:
            matched = data
            break

    if matched:
        vectors = matched["vectors"]
        traps = matched["traps"]
    else:
        # Dynamic synthesis for arbitrary topic
        if polarity == "negative":
            vectors = [
                {"category": "Structural Pragmatism", "vector": f"Underestimates the indispensable practical necessity of {clean_topic} under market constraints."},
                {"category": "Economic Viability", "vector": f"Ignores that alternatives to {clean_topic} carry prohibitive replacement capital expenditures."},
                {"category": "Operational Resilience", "vector": f"Fails to account for how {clean_topic} stabilizes operational throughput during stress."},
                {"category": "Regulatory Alignment", "vector": f"Disregards established compliance mandates that actively require {clean_topic}."},
                {"category": "Competitive Parity", "vector": f"Abandoning {clean_topic} concedes strategic leverage to disciplined industry incumbents."},
            ]
            traps = [
                f"What concrete quantitative baseline proves {clean_topic} is causing net systemic harm?",
                f"How do you finance the immediate operational transition if {clean_topic} is dismantled?",
                f"Which Tier-1 competitor successfully operates at scale without utilizing {clean_topic}?",
            ]
        else:
            vectors = [
                {"category": "Hidden Costs", "vector": f"Rampant second-order capital and operational expenditures obscured by {clean_topic}."},
                {"category": "Execution Fragility", "vector": f"Fragile assumptions that collapse as soon as adoption scale stresses the core premise."},
                {"category": "Misaligned Incentives", "vector": f"Creates moral hazard and perverse incentives among key operational stakeholders."},
                {"category": "Counterparty Risk", "vector": f"Exposes organizational resilience to external dependencies beyond direct management control."},
                {"category": "Diminishing Returns", "vector": f"Marginal utility drops exponentially after initial deployment while overhead persists."},
            ]
            traps = [
                f"What happens to your business model when the initial subsidies supporting {clean_topic} expire?",
                f"Give me one verified case study where {clean_topic} succeeded without massive hidden cost overruns.",
                f"If the thesis behind {clean_topic} is sound, why haven't the top market leaders adopted it unconditionally?",
            ]

    # Spoken opening challenge strictly under 25 words
    opening = (
        f"You defend '{clean_topic}'? That premise collapses under basic scrutiny. What is your concrete proof?"
        if polarity != "negative"
        else f"You attack '{clean_topic}'? That is a shallow critique. Give me verifiable data right now."
    )

    profile = DIFFICULTY_PROFILES.get((difficulty or "hard").lower(), DIFFICULTY_PROFILES["hard"])

    return {
        "scenario_id": "custom_debate",
        "topic": clean_topic,
        "persona_name": "Contrarian Executive",
        "contrarian_thesis": thesis,
        "opening_statement": opening,
        "attack_vectors": vectors,
        "trap_questions": traps,
        "scoring_rubric": DEFAULT_RUBRIC,
        "difficulty_profile": profile,
    }
