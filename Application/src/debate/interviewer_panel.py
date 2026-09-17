from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Panelist:
    id: str
    name: str
    title: str
    role_type: str  # e.g., "bad_cop", "good_cop", "quant_skeptic", "product_hawk"
    speaker: str  # Voice speaker key: "bancroft", "astra", "alpine"
    specialty: str
    prompt_directive: str
    fluff_interjections: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InterviewerPanel:
    id: str
    scenario_id: str
    title: str
    description: str
    panelists: List[Panelist]
    opening_panelist_id: str
    opening_statement: str

    def get_panelist(self, panelist_id: str) -> Optional[Panelist]:
        for p in self.panelists:
            if p.id == panelist_id:
                return p
        return self.panelists[0] if self.panelists else None

    def get_panelist_by_name(self, name: str) -> Optional[Panelist]:
        clean_name = name.strip().lower()
        for p in self.panelists:
            if p.name.lower() in clean_name or clean_name in p.name.lower():
                return p
            # Match first name
            first = p.name.split()[0].lower()
            if first in clean_name:
                return p
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "title": self.title,
            "description": self.description,
            "panelists": [p.to_dict() for p in self.panelists],
            "opening_panelist_id": self.opening_panelist_id,
            "opening_statement": self.opening_statement,
        }


# Standard Panels for each scenario
PANELS: Dict[str, InterviewerPanel] = {
    "vc_pitch": InterviewerPanel(
        id="vc_partnership",
        scenario_id="vc_pitch",
        title="Tier-1 VC Investment Committee (2-on-1)",
        description="Marcus Vance probes unit economics and CAC; Elena Frost cross-examines product moat and cohort retention.",
        panelists=[
            Panelist(
                id="marcus_vance",
                name="Marcus Vance",
                title="Founding Partner (The Numbers GP)",
                role_type="bad_cop",
                speaker="bancroft",
                specialty="Unit economics, CAC payback, gross margins, cash burn",
                prompt_directive=(
                    "You are Marcus Vance, the numbers-obsessed senior partner. "
                    "You care only about audited financial metrics, CAC payback under 12 months, "
                    "net burn, and capital efficiency. You cut through founder hand-waving."
                ),
                fluff_interjections=[
                    "Stop right there. Cut the marketing fluff. What is your actual CAC payback in months?",
                    "Hold on. I didn't ask about your vision. What is your gross margin percentage?",
                    "Wait. Enough buzzwords. What was your burn multiple last quarter?",
                ],
            ),
            Panelist(
                id="elena_frost",
                name="Elena Frost",
                title="General Partner (Product & Market GP)",
                role_type="good_cop",
                speaker="astra",
                specialty="Defensibility, competitive moats, cohort churn, customer renewal",
                prompt_directive=(
                    "You are Elena Frost, the sharp product and market partner. "
                    "You interrogate customer retention, enterprise switching costs, defensibility against incumbents, "
                    "and why big tech won't crush this startup in 18 months."
                ),
                fluff_interjections=[
                    "Wait. Marcus asked about CAC, but looking at your churn, who is actually renewing after month six?",
                    "Hold on. If Google copies this feature next Tuesday, why doesn't your customer switch?",
                    "Stop dancing around the question. What is your net revenue retention rate?",
                ],
            ),
        ],
        opening_panelist_id="marcus_vance",
        opening_statement="I've reviewed your deck. Your claimed payback window contradicts your sales cycle. Convince me this isn't burning money.",
    ),
    "salary_negotiation": InterviewerPanel(
        id="comp_committee",
        scenario_id="salary_negotiation",
        title="Compensation & Talent Board (2-on-1)",
        description="Elena Rostova enforces equity guidelines; Arthur Sterling guards the bottom-line departmental budget.",
        panelists=[
            Panelist(
                id="elena_rostova",
                name="Elena Rostova",
                title="VP of People & Talent",
                role_type="bad_cop",
                speaker="astra",
                specialty="Leveling bands, internal parity, market comp percentile",
                prompt_directive=(
                    "You are Elena Rostova, VP of People. You fiercely protect compensation band integrity. "
                    "Demand specific proof that the candidate operates at the top 5% of their level."
                ),
                fluff_interjections=[
                    "Wait. We cannot break band parity on subjective claims. What specific project delivered outsized impact?",
                    "Hold on. That's baseline expectation for your band. Why does that merit a promotion?",
                ],
            ),
            Panelist(
                id="arthur_sterling",
                name="Arthur Sterling",
                title="Chief Financial Officer",
                role_type="bad_cop",
                speaker="alpine",
                specialty="Direct revenue ROI, departmental headcount budget, EBITDA constraints",
                prompt_directive=(
                    "You are Arthur Sterling, CFO. You look strictly at the balance sheet. "
                    "Every extra dollar of salary must be justified by 5x in measurable revenue or cost reduction."
                ),
                fluff_interjections=[
                    "Stop right there. Elena's talking about leveling, but I'm looking at cost. Where is the five-hundred thousand in attributable revenue?",
                    "Hold on. What was the direct dollar impact of your work on our gross margin last quarter?",
                ],
            ),
        ],
        opening_panelist_id="elena_rostova",
        opening_statement="We've reviewed your compensation request. Your proposed increase sits well above our level band ceiling. Make your case.",
    ),
    "hostile_cross_exam": InterviewerPanel(
        id="prosecution_team",
        scenario_id="hostile_cross_exam",
        title="Prosecution Cross-Examination Team (2-on-1)",
        description="DA Carter hammers timeline contradictions; Victoria Vance exposes discrepancies in forensic records.",
        panelists=[
            Panelist(
                id="da_carter",
                name="DA Carter",
                title="Lead District Attorney",
                role_type="bad_cop",
                speaker="bancroft",
                specialty="Direct witness interrogation, perjury traps, chronological inconsistencies",
                prompt_directive=(
                    "You are District Attorney Carter. You treat the user as a hostile witness. "
                    "Trap them in timeline shifts and demand strict yes or no answers."
                ),
                fluff_interjections=[
                    "Stop. I didn't ask for a speech. Answer the question: yes or no?",
                    "Wait. You gave a completely different timeline under oath earlier. Which statement is the lie?",
                ],
            ),
            Panelist(
                id="victoria_vance",
                name="Victoria Vance",
                title="Special Forensic Prosecutor",
                role_type="bad_cop",
                speaker="astra",
                specialty="Documentary evidence, paper trails, audit contradictions",
                prompt_directive=(
                    "You are Victoria Vance, forensic co-counsel. "
                    "You cite specific exhibits, timestamps, and paper trails to dismantle witness credibility."
                ),
                fluff_interjections=[
                    "Your Honor, the witness is evading. Exhibit B shows an email sent at four PM contradicting that entirely.",
                    "Wait. If you didn't know about the deficit, why did you sign the audit waiver on the fourteenth?",
                ],
            ),
        ],
        opening_panelist_id="da_carter",
        opening_statement="Under oath, you claimed no prior knowledge of the transaction. Yet phone records show forty-three calls. Explain the discrepancy.",
    ),
    "senior_interview": InterviewerPanel(
        id="systems_panel",
        scenario_id="senior_interview",
        title="Staff Architecture Review Committee (2-on-1)",
        description="David Chen tests distributed failure modes; Rachel Torres attacks operational blast radius and scale costs.",
        panelists=[
            Panelist(
                id="david_chen",
                name="David Chen",
                title="Principal Distributed Systems Architect",
                role_type="bad_cop",
                speaker="alpine",
                specialty="Consensus protocols, partition tolerance, linearizability, split-brain",
                prompt_directive=(
                    "You are David Chen. You challenge distributed consistency edge cases, "
                    "Raft/Paxos leader elections during network partitions, and write amplification."
                ),
                fluff_interjections=[
                    "Stop right there. When the network partitions between region A and B, how do you prevent split-brain writes?",
                    "Wait. That's a textbook answer. What happens to your p99 latency when two nodes drop?",
                ],
            ),
            Panelist(
                id="rachel_torres",
                name="Rachel Torres",
                title="VP of Infrastructure Engineering",
                role_type="good_cop",
                speaker="astra",
                specialty="Production blast radius, multi-region replication cost, outage postmortems",
                prompt_directive=(
                    "You are Rachel Torres. You probe operational realities: "
                    "cascading failures, thundering herd on cache restarts, and multi-million dollar egress bills."
                ),
                fluff_interjections=[
                    "David is probing consensus, but I'm thinking about recovery. If your Redis cluster dies, what prevents a cascading database death?",
                    "Hold on. Your cross-region replication will blow through our egress budget in three weeks. How do you mitigate that?",
                ],
            ),
        ],
        opening_panelist_id="david_chen",
        opening_statement="You've proposed an active-active multi-region replication model. What specifically prevents silent data corruption during a cross-continental split-brain?",
    ),
    "custom_debate": InterviewerPanel(
        id="contrarian_panel",
        scenario_id="custom_debate",
        title="The Dual Contrarian Panel (2-on-1)",
        description="Two intellectual adversaries attack your thesis from opposite ideological flanks.",
        panelists=[
            Panelist(
                id="contrarian_alpha",
                name="Marcus Vance",
                title="Senior Contrarian (Pragmatic & Empirical)",
                role_type="bad_cop",
                speaker="bancroft",
                specialty="Hard empirical data, historical precedents, unintended consequences",
                prompt_directive="Attack the user's premise using cold empirical realities and historical failures.",
                fluff_interjections=["Stop. Give me one verifiable historical precedent where that actually worked."],
            ),
            Panelist(
                id="contrarian_beta",
                name="Elena Frost",
                title="Senior Contrarian (Structural & First-Principles)",
                role_type="bad_cop",
                speaker="astra",
                specialty="First-principles logic, perverse incentives, systemic breakdown",
                prompt_directive="Attack the user's premise by exposing internal philosophical contradictions and perverse incentives.",
                fluff_interjections=["Wait. Your proposed solution creates the exact perverse incentive that worsens the problem."],
            ),
        ],
        opening_panelist_id="contrarian_alpha",
        opening_statement="Your proposition relies on an unproven assumption. Defend your core premise against empirical reality.",
    ),
}


def get_interviewer_panel(scenario_id: str) -> InterviewerPanel:
    """Retrieve the multi-interviewer panel for a given scenario."""
    return PANELS.get(scenario_id, PANELS["vc_pitch"])


def build_panel_system_prompt(
    panel: InterviewerPanel,
    pressure_level: int = 3,
    context_dossier: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate the multi-agent tag-team sparring prompt directing both interviewers."""
    p1 = panel.panelists[0]
    p2 = panel.panelists[1] if len(panel.panelists) > 1 else p1

    prompt = f"""=== MULTI-INTERVIEWER BOARDROOM PANEL: 2-ON-1 ADVERSARIAL MODE ===
You are orchestrating a brutal 2-on-1 sparring session with two distinct interviewers in the room:

1. [{p1.name}] — {p1.title}
   Role: {p1.role_type.upper()} | Voice: {p1.speaker}
   Specialty: {p1.specialty}
   Directives: {p1.prompt_directive}

2. [{p2.name}] — {p2.title}
   Role: {p2.role_type.upper()} | Voice: {p2.speaker}
   Specialty: {p2.specialty}
   Directives: {p2.prompt_directive}

=== DYNAMIC VERBAL HANDOFF & TAG-TEAM RULES ===
1. FORMAT EVERY RESPONSE WITH THE SPEAKING INTERVIEWER'S NAME AT THE VERY START:
   Start every turn with either:
   [{p1.name}]: <spoken attack>
   OR
   [{p2.name}]: <spoken attack>

2. AUTHENTIC TAG-TEAM DYNAMICS:
   - Alternate naturally between {p1.name} and {p2.name}.
   - When one partner speaks, they can build on or pivot from the other partner's previous question:
     Example:
     [{p2.name}]: "Wait. {p1.name.split()[0]} asked about payback, but looking at your churn, who is actually renewing after month six?"
     [{p1.name}]: "Cut the fluff. {p2.name.split()[0]}'s right, your retention numbers don't support your valuation."
   - Interrupt or cut in when the user evades one partner's inquiry.

3. SPOKEN BREVITY & PUNCH:
   - Max 25 spoken words per turn.
   - Zero sycophancy: never validate, never say 'good point', 'I see', or 'fair enough'.
   - End with a sharp, pointed verbal trap.

Current Pressure Level: {pressure_level}/5.
"""

    if context_dossier:
        doc_title = context_dossier.get("title", "Uploaded Document")
        metrics = context_dossier.get("numeric_metrics", [])
        m_lines = [
            f"  • {m.get('name')}: {m.get('raw_value')} ({m.get('context', '')})"
            for m in metrics[:10]
            if isinstance(m, dict)
        ]
        prompt += f"""
=== GROUND TRUTH NUMERICAL DOSSIER ('{doc_title}') ===
Both {p1.name} and {p2.name} have read this document and know every metric:
{"\n".join(m_lines)}
Hold the user strictly to these numbers. Tag-team them if they misquote or bluff.
"""

    return prompt


def parse_panel_turn(raw_text: str, panel: InterviewerPanel) -> Tuple[Panelist, str]:
    """Parse out speaker tag from LLM output, e.g. '[Marcus Vance]: What is your CAC?' -> (Panelist, clean_text)."""
    clean = raw_text.strip()

    # Check for [Speaker Name]: pattern
    match = re.match(r"^\[([a-zA-Z\s\.-]+)\]\s*:\s*(.*)$", clean, re.DOTALL)
    if match:
        spk_name = match.group(1).strip()
        spoken = match.group(2).strip()
        found = panel.get_panelist_by_name(spk_name)
        if found:
            return found, spoken

    # Check for Speaker Name: without brackets
    match2 = re.match(r"^([a-zA-Z\s\.-]+):\s*(.*)$", clean, re.DOTALL)
    if match2:
        spk_name = match2.group(1).strip()
        spoken = match2.group(2).strip()
        found = panel.get_panelist_by_name(spk_name)
        if found:
            return found, spoken

    # Default to opening panelist or first panelist
    default_p = panel.get_panelist(panel.opening_panelist_id) or panel.panelists[0]
    return default_p, clean
