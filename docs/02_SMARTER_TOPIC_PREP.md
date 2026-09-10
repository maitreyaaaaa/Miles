# Feature Specification: Smarter Custom Topic Prep

## 1. Problem Statement
Currently, entering a custom topic generates an adversarial thesis and opening statement. However, in true adversarial debate, high-caliber opponents don't just react—they arrive with a prepared dossier:
- Specific angles of attack (economic, ethical, practical, technical, operational).
- Concealed traps and rhetorical follow-up questions designed to dismantle the user's position.
- A customized scoring rubric tailored to the specific controversy of the topic.

## 2. Solution Overview
When the user submits a custom topic (or edits an existing one), Miles runs a **Deep Adversarial Topic Dossier Generator**.
While the user watches the evocative, atmospheric "thinking" words (e.g. *apophenia, palimpsest, susurrus, numinous*), the backend LLM compiles a structured **Battle Dossier**:
1. **Contrarian Thesis**: The sharp, diametric stance Miles will take.
2. **Opening Salvo**: A high-impact opening challenge (<25 words) forcing the user to commit.
3. **5 Concrete Attack Vectors**: Categorized angles of vulnerability (e.g., unit economics, scalability, moral hazard, compliance, adoption).
4. **Trap Follow-Up Questions**: Pre-computed verbal counter-attacks if the user evades.
5. **Topic-Specific Scoring Rubric**: The exact criteria used during the final debrief.
6. **Difficulty Profile**: Calibrated pressure scaling and acceptable disfluency tolerance.

---

## 3. Data Schema & REST Contract

### Request: `POST /api/scenarios/custom`
```json
{
  "topic": "Remote work is superior to in-office work for technology companies",
  "difficulty": "ruthless",
  "persona_tone": "calm_ruthless"
}
```

### Response: Dossier Payload
```json
{
  "scenario_id": "custom_debate",
  "topic": "Remote work is superior to in-office work for technology companies",
  "persona_name": "Contrarian Executive",
  "contrarian_thesis": "Remote work erodes junior engineer development, destroys spontaneous cross-discipline innovation, and leads to transactional mercenary cultures.",
  "opening_statement": "Remote work feels productive until your innovation pipeline dries up. How do you train junior talent when senior engineers are silent avatars?",
  "attack_vectors": [
    {
      "category": "Mentorship & Culture",
      "vector": "Tacit knowledge transfer and junior developer skill degradation without physical osmosis."
    },
    {
      "category": "Innovation Velocity",
      "vector": "Loss of serendipitous problem-solving in unstructured hall discussions."
    },
    {
      "category": "Mercenary Attrition",
      "vector": "Zero company loyalty leading to 3x higher turnover and multi-job moonlighting."
    },
    {
      "category": "Security & IP",
      "vector": "Exfiltration risk and compromised home network hygiene."
    },
    {
      "category": "Operational Overhead",
      "vector": "Meeting bloat and asynchronous communication paralysis replacing simple 5-minute alignment."
    }
  ],
  "trap_questions": [
    "Name three senior architects at your company who learned systems design exclusively through asynchronous Slack threads.",
    "If remote productivity is higher, why did the top 5 cloud hyperscalers institute return-to-office mandates?",
    "When a critical production incident occurs, does asynchronous messaging resolve it faster than war rooms?"
  ],
  "scoring_rubric": {
    "evidence_weight": 0.35,
    "cadence_weight": 0.25,
    "composure_weight": 0.25,
    "brevity_weight": 0.15
  },
  "difficulty_profile": {
    "hesitation_threshold_sec": 1.8,
    "rambling_threshold_sec": 9.0,
    "filler_tolerance": 1,
    "adversarial_intensity": 5
  }
}
```

---

## 4. Frontend Experience: Evocative Calibration Stream

As the dossier compiles over ~1.5 to 2.5 seconds:
1. **Evocative Thinking Cycle**: Cycles through esoteric philosophical terms reflecting adversarial cognition:
   - `apophenia`: pattern recognition in arguments
   - `palimpsest`: overwriting weak assumptions
   - `susurrus`: subtle rhetorical undertones
   - `liminality`: boundary-state cognitive calibration
   - `aporia`: state of puzzled contradiction
