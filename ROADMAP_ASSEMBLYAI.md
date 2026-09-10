# Miles — AssemblyAI Hackathon Master Upgrade Blueprint

> **Master Architecture, Specifications, and Implementation Roadmap**  
> Unifying Full-Duplex Spoken Adversarial Sparring with AssemblyAI Audio Intelligence, High-Stakes Scenario Packs, and Training Replay Dynamics.

---

## 🎯 Executive Vision: The Ultimate Voice Training Platform

Miles transforms from a high-speed adversarial voice demo into a **production-grade executive communication training platform**.

While the primary voice loop continues to leverage sub-second full-duplex conversational audio, the AssemblyAI upgrade layers in **deep acoustic and linguistic intelligence**:
- **Zero-Friction Voice Preflight**: Eliminates browser audio setup failures before entering battle.
- **Deep Scenario Preparation**: Dynamically compiles multi-angle attack dossiers, trap questions, and scoring rubrics for any topic.
- **AssemblyAI Word-Level Audio Intelligence**: Unlocks micro-hesitation mapping, domain vocabulary boosting, talk-time ratio tracking, and sentiment trajectory.
- **Debrief 2.0 & Interactive Replay**: Removes distracting metrics from the live debate; surfaces profound retrospective analytics including "Weakest vs. Strongest Answer", "What You Should Have Said", and timeline scrubbing across critical debate moments.
- **8 Scenario Packs & 5 Adversarial Personas**: Expands from startup pitching to media crisis management, boardroom activism, enterprise sales objection handling, and courtroom grilling.
- **Judge & Demo Evidence Mode (?demo=1)**: A discrete, high-density telemetry console exposing real-time API health, streaming latency, and interruption metrics for hackathon evaluation.

---

## 🗺️ Master Architecture & Data Flow

`
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    BROWSER CLIENT (REACT 18)                                │
│                                                                                             │
│  ┌──────────────────────┐   ┌─────────────────────────────┐   ┌──────────────────────────┐  │
│  │ 1. Voice Preflight   │──▶│ 2. Live Sparring Stage      │──▶│ 3. Debrief 2.0 & Replay  │  │
│  │  • Mic RMS gauge     │   │  • Fluid visual presence    │   │  • Whole-session report  │  │
│  │  • Audio chime test  │   │  • Real-time AI subtitles   │   │  • Weakest / strongest   │  │
│  │  • API health check  │   │  • Talk-time dominance ratio│   │  • "What you should say" │  │
│  │  • Auto-pass         │   │  • Clean immersive canvas   │   │  • Audio moment replay   │  │
│  └──────────────────────┘   └──────────────┬──────────────┘   └──────────────────────────┘  │
│                                            │                                                │
│                                            │ WebSocket (ws://host/ws/debate)                │
└────────────────────────────────────────────┼────────────────────────────────────────────────┘
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                               FASTAPI FULL-DUPLEX WEBSOCKET SERVER                          │
│                                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              ASSEMBLYAI STREAMING v3 CLIENT                           │  │
│  │  • Universal-Streaming v3 over WebSocket with short-lived token auth                  │  │
│  │  • Word-Level Timestamps: (start, end, confidence) for micro-hesitation mapping       │  │
│  │  • Domain Vocabulary Boosting: Injects scenario-specific keywords & terminology      │  │
│  │  • Real-Time Speech Onset Detection for instantaneous barge-in triggers               │  │
│  └──────────────────────────────────────────┬────────────────────────────────────────────┘  │
│                                             ▼                                               │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                           ACTIVE PRESENCE & INTERRUPTION ENGINE                       │  │
│  │  • Dead air monitor (>2.3s)                                                           │  │
│  │  • Mid-speech freeze monitor (>2.0s)                                                  │  │
│  │  • Rambling duration monitor (>11s)                                                   │  │
│  │  • Sub-1ms user barge-in audio cut-off & memory truncation                            │  │
│  └──────────────────────────────────────────┬────────────────────────────────────────────┘  │
│                                             ▼                                               │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                           PIPELINED ADVERSARIAL LLM ENGINE                            │  │
│  │  • OpenRouter / OpenAI: Meta-Llama 3.3 70B (Low-latency streaming sparring)           │  │
│  │  • Clause/Sentence buffer: Emits audio before complete response finishes              │  │
│  │  • 5 Persona Stylistic Modifiers (Calm Ruthless, Skeptical VC, Relentless Friendly...)│  │
│  └──────────────────────────────────────────┬────────────────────────────────────────────┘  │
│                                             ▼                                               │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                               RIME CODA NEURAL TTS ENGINE                             │  │
│  │  • modelId: coda with persona speakers (alpine, astra, bancroft)                      │  │
│  │  • Persistent HTTP/2 keep-alive connection pool                                       │  │
│  │  • Instant stream cancellation on interruption                                        │  │
│  └───────────────────────────────────────────────────────────────────────────────────────┘  │
│                                             │                                               │
│  ┌──────────────────────────────────────────┴────────────────────────────────────────────┐  │
│  │                               POST-DEBATE INTELLIGENCE                                │  │
│  │  • AssemblyAI LeMUR / LLM Whole-Transcript Evaluation Engine                          │  │
│  │  • Timestamped moment indexer for interactive replay                                  │  │
│  │  • Speech cadence curve & semantic filler breakdown                                   │  │
│  └───────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
`

---

## 📑 Specification Index & Detailed Technical Plans

We have broken down each component into its own dedicated specification document in docs/:

| Document | Component | Key Highlights |
| :--- | :--- | :--- |
| [01_VOICE_PREFLIGHT.md](docs/01_VOICE_PREFLIGHT.md) | **Voice Preflight Screen** | Mic hardware test, browser audio chime check, WebSocket latency probe, Rime & AssemblyAI status, 1-click self-test bypass. |
| [02_SMARTER_TOPIC_PREP.md](docs/02_SMARTER_TOPIC_PREP.md) | **Smarter Custom Topic Prep** | Opponent thesis, 5 attack vectors, trap questions, scoring rubric, difficulty profile, LLM prompt engineering, visual progress stream. |
| [03_ASSEMBLYAI_INTELLIGENCE.md](docs/03_ASSEMBLYAI_INTELLIGENCE.md) | **AssemblyAI Audio Intelligence** | Word-level timestamps, micro-hesitation gap detection, domain keyterm boosting, talk-time dominance HUD, sentiment trajectory. |
| [04_DEBRIEF_2_AND_REPLAY.md](docs/04_DEBRIEF_2_AND_REPLAY.md) | **Debrief 2.0 & Replay Mode** | Clean live debate screen, post-debate deep analysis, weakest vs strongest answers, "what you should have said", audio timeline scrubber. |
| [05_SCENARIOS_AND_PERSONAS.md](docs/05_SCENARIOS_AND_PERSONAS.md) | **8 Scenarios & 5 Personas** | 8 high-stakes pressure packs (VC, Salary, Legal, Sales, Media, Board, Interview), 5 adversarial voice tones (Calm Ruthless, etc.). |
| [06_JUDGE_DEMO_MODE.md](docs/06_JUDGE_DEMO_MODE.md) | **Hidden Demo Evidence Mode** | ?demo=1 / Ctrl+Shift+D diagnostics console, live event stream, Rime & AssemblyAI telemetry, sub-millisecond barge-in benchmarks. |

---

## 🗓️ Implementation Phases (Ready for Build Once Confirmed)

### Phase 1: Robustness & Demo Readiness
1. **Voice Preflight Modal**: Pre-debate audio & connection verification.
2. **Hidden Demo Mode (?demo=1)**: Telemetry panel for hackathon presentation.

### Phase 2: AssemblyAI Audio Intelligence Core
1. **AssemblyAI v3 Word Timestamps**: Capture start, end, and confidence per word.
2. **Vocabulary Boosting**: Inject domain terms based on selected scenario.
3. **Micro-Hesitation & Talk-Time Calculator**: Track speech gaps between words and conversational balance.

### Phase 3: Content Breadth & Dynamic Topic Engine
1. **Smarter Topic Prep Engine**: Generate complete 5-vector dossiers for custom topics.
2. **8 Scenario Packs & 5 Persona Styles**: Expand system prompts and TTS voice configs.

### Phase 4: Training & Training Analytics
1. **Clean Live UI**: Strip out distractors during active debate.
2. **Debrief 2.0**: Surface weakest/strongest answers and executive reframings.
3. **Interactive Moment Replay**: Enable timeline scrubbing to specific points of friction.

---
