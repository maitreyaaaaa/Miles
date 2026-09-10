# Miles: Full-Duplex Adversarial Voice Sparring Partner

> **A high-stakes verbal negotiation & debate sparring partner that tests your composure, speech cadence, and logical resilience under intense psychological pressure.**

Built concurrently for two premier voice hackathons:
1. **AssemblyAI Voice Agent Hackathon (lablab.ai):** Powers real-time streaming speech recognition via Universal-Streaming v3 (sub-200ms latency), live filler word detection ("um", "uh", "like", "basically"), speech cadence/WPM tracking, and composure intelligence scoring.
2. **DataForge Pathway x Rime Hackathon:** Powers ultra-low latency spoken output via Rime neural streaming TTS, solving the hardest voice challenge: **Full-Duplex Interruption & Pressure Dynamics (<100ms barge-in cut-off)**.

---

## 🏛️ Architecture & Full-Duplex Audio Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            WEB BROWSER (Codex UI)                           │
│  • Web Audio API (navigator.mediaDevices.getUserMedia at 16kHz PCM mono)    │
│  • Real-Time Pressure & Composure HUD (0-100 score, WPM gauge, filler tally)│
│  • Sub-100ms Instant Audio Queue Flush on User Barge-in                     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ WebSocket (ws://localhost:8000/ws/debate)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     FASTAPI FULL-DUPLEX WEBSOCKET SERVER                    │
│                                                                             │
│  ┌─────────────────────────┐                   ┌─────────────────────────┐  │
│  │  AssemblyAI Streaming   │                   │    Rime Neural TTS      │  │
│  │ • Universal-Streaming v3│                   │ • users.rime.ai/v1/tts  │  │
│  │ • Live partials & finals│                   │ • Stream cancel <5ms    │  │
│  │ • Disfluency detection  │                   │ • Windows SAPI fallback │  │
│  └────────────┬────────────┘                   └────────────▲────────────┘  │
│               │ Transcripts                                 │ Audio Chunks  │
│               ▼                                             │               │
│  ┌──────────────────────────────────────────────────────────┴────────────┐  │
│  │                   FULL-DUPLEX INTERRUPTION MANAGER                    │  │
│  │ • User Barge-in: Sub-100ms audio cancellation & memory truncation     │  │
│  │ • AI Interruption: Instant cut-off when user stalls (>2.2s) or waffling│  │
│  └────────────────────────────┬──────────────────────────────────────────┘  │
│                               │ Context & Events                            │
│                               ▼                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                  ADVERSARIAL LLM DEBATE ENGINE                        │  │
│  │ • Anti-Sycophancy Policy: Zero politeness / no "good points"          │  │
│  │ • Spoken Brevity (<25 words per turn) ending with pointed traps       │  │
│  │ • Dynamic Contrarian Inversion for ANY custom user topic              │  │
│  │ • Multi-Provider Connector (OpenAI gpt-4o-mini / Gemini / Anthropic)  │  │
│  │ • Real-time Composure & Speech Cadence Scoring (0-100 + Debrief)      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎭 Debate Personas & Modes

1. **The Skeptical Tier-1 VC (`vc_pitch`):**
   - **Marcus Vance**: Relentlessly grills your startup pitch on CAC, LTV, payback windows, defensibility, and competitive moats.
2. **The Hardball VP of Talent (`salary_negotiation`):**
   - **Elena Rostova**: Hardball compensation negotiation. Counters aggressive salary demands, protects equity caps, and demands proof of revenue impact.
3. **The Hostile Legal Prosecutor (`hostile_cross_exam`):**
   - **DA Carter**: Courtroom cross-examination. Pounces on inconsistencies, timeline gaps, and hesitations.
4. **Open Freeform Contrarian Debate (`custom_debate`):**
   - **Any topic the user wants!** The user types or speaks a topic (e.g. *"Remote work is superior"*, *"AI will replace programmers"*), and the AI immediately detects the stance, inverts it, and takes an aggressive contrarian position.

---

## ⚡ Full-Duplex Interruption (<100ms Barge-in)

In verbal sparring, rigid turn-taking ruins realism. Miles implements dual-direction interruption:
- **User Barge-in:** When the user interrupts the AI mid-sentence, active audio streaming terminates in **< 1 ms**, in-flight buffers are purged, and the AI's conversation memory truncates so it only recalls what was heard before the cut-off.
- **AI Interruption:** If the user hesitates for $> 2.2\text{ s}$, stutters on 3+ filler words ("um", "like", "basically"), or uses empty corporate buzzwords ("synergy", "paradigm"), the AI interrupts with a sharp counter-challenge.

---

## 🚀 Quick Start

### 1. Requirements
- Windows 10 / 11, macOS, or Linux
- Python 3.12+
- Microphone

### 2. Install Dependencies
```powershell
cd Application
pip install -e .
```

### 3. Configure `.env`
Ensure your `.env` file contains your API keys:
```env
ASSEMBLYAI_API_KEY=your_assemblyai_key
RIME_API_KEY=your_rime_key       # Optional (falls back to local voice engine if omitted)
OPENAI_API_KEY=your_openai_key   # Optional (falls back to Gemini or heuristic offline sparring engine)
GEMINI_API_KEY=your_gemini_key   # Optional
```

### 4. Start Backend Server
```powershell
uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
# or:
python main.py
```

- **Interactive API Documentation:** `http://localhost:8000/docs`
- **Live WebSocket:** `ws://localhost:8000/ws/debate`

---

## 🧪 Verification & Benchmark Suite

### Run All Unit & Integration Tests (22 Tests)
```powershell
pytest -v
```

### Run Barge-in Latency Benchmark (DataForge Evidence)
```powershell
python benchmark_interruption.py
```
Measures 10 continuous trials of in-flight speech interruption with microsecond precision. Demonstrates average cut-off latency of **< 0.2 ms**, well within the sub-100ms hackathon threshold.

See [`RIME_EVIDENCE.md`](./RIME_EVIDENCE.md) for full acceptance test criteria and submission data.
See [`CODEX_CONTEXT.md`](./CODEX_CONTEXT.md) and [`FRONTEND_BROWSER_GUIDE.md`](./FRONTEND_BROWSER_GUIDE.md) for frontend integration guides.
