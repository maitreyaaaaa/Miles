# Feature Specification: AssemblyAI Speech & Audio Intelligence

## 1. Overview & Hackathon Alignment
AssemblyAI Universal-Streaming v3 powers Miles's ultra-low latency acoustic front-end. For the AssemblyAI Voice Agent Hackathon, we elevate this integration from basic speech-to-text into an **Acoustic & Semantic Intelligence Engine**:
1. **Word-Level Millisecond Timestamps**: Every word emitted by AssemblyAI contains `start` and `end` millisecond offsets.
2. **Micro-Hesitation Gap Mapping**: Measuring the acoustic silence between words (e.g. 850ms pause before asserting a number indicates hesitation).
3. **Domain Vocabulary Boosting**: Dynamically injecting scenario-specific terminology (e.g., `["EBITDA", "CAC", "LTV", "indemnification", "severability"]`) into the streaming session to guarantee 100% transcription accuracy.
4. **Talk-Time Ratio & Conversational Dominance**: Measuring cumulative speaking duration between user and adversary to display airtime balance.
5. **Sentiment & Stress Trajectory**: Tracking acoustic confidence vs defensiveness across rounds to dynamically adapt opponent pressure.

---

## 2. Technical Capabilities & Integration

### A. Word-Level Timestamp Parsing
In `Application/src/voice/assemblyai_stream.py`:
```python
# Each word in the AssemblyAI Turn event contains:
# {"word": "CAC", "start": 1240, "end": 1580, "confidence": 0.98}
for i in range(len(words) - 1):
    current_end = words[i]["end"]
    next_start = words[i + 1]["start"]
    inter_word_gap_ms = next_start - current_end
    if inter_word_gap_ms > 750:
        # Micro-hesitation detected inside a single utterance
        hesitation_events.append({
            "word_before": words[i]["word"],
            "word_after": words[i + 1]["word"],
            "gap_ms": inter_word_gap_ms,
            "timestamp_ms": current_end
        })
```

### B. Scenario-Specific Vocabulary Boosting
When initializing the AssemblyAI WebSocket stream, inject domain-specific keywords into the session configuration:
- **VC Pitch**: `["CAC", "LTV", "churn rate", "payback window", "EBITDA", "TAM", "SAM", "burn multiple", "runway", "seed round"]`
- **Salary Negotiation**: `["base salary", "equity grant", "RSUs", "vesting schedule", "cliff", "strike price", "409A valuation", "signing bonus"]`
- **Hostile Cross-Exam**: `["subpoena", "affidavit", "admissibility", "perjury", "chain of custody", "exculpatory", "deposition", "preponderance"]`
- **Sales Objection**: `["procurement", "annual contract value", "SLA", "SOC2 compliance", "seat licensing", "implementation timeline"]`

### C. Conversational Dominance & Talk-Time HUD
A minimal visual widget on the debate stage tracking the ratio of spoken airtime:
```
[ User: 58% ████████████░░░░░░░░ Miles: 42% ]
```
- If User < 30%: User is being steamrolled by the adversary.
- If User > 75%: User is rambling and monopolizing airtime, inviting an instant interruption.

---

## 3. Data Schema & Events

### WebSocket Telemetry Event: `speech_intelligence`
```json
{
  "type": "speech_intelligence",
  "round": 2,
  "user_talk_time_sec": 18.4,
  "ai_talk_time_sec": 12.1,
  "dominance_ratio": 0.60,
  "micro_hesitations": [
    {
      "gap_ms": 1120,
      "context": "our CAC is [1120ms] forty dollars",
      "severity": "high"
    }
  ],
  "confidence_mean": 0.96,
  "stress_indicator": "elevated"
}
```
