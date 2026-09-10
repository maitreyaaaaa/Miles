# CODEX_CONTEXT.md — Miles Architecture & Frontend Integration Spec

> **For Codex / Frontend Builder**: Read this document to understand what the Python backend does, the exact WebSocket/REST contracts, and the UI components you need to generate for the **Web Browser**.

---

## 1. Executive Brief (TL;DR)

- **Project Name:** Miles
- **Core Concept:** An adversarial verbal negotiation & debate sparring partner. Rather than being a polite assistant, the AI acts as a ruthless adversary testing the user's verbal composure, logic, and persuasion under pressure.
- **Hackathon Targets:**
  1. **AssemblyAI Voice Agent Hackathon (lablab.ai):** Powers real-time streaming speech-to-text (sub-200ms latency), filler word detection ("um", "uh"), speech cadence/WPM tracking, and speech intelligence scoring.
  2. **DataForge Pathway x Rime Hackathon:** Powers ultra-low latency spoken output via Rime TTS, solving the hardest voice challenge: **Full-Duplex Interruption & Pressure Dynamics** (sub-100ms barge-in cut-off).
- **Scope Split:**
  - **Backend (Python / FastAPI in `D:\Voice AI\Application`):** FastAPI WebSocket server, AssemblyAI streaming STT, Rime neural streaming TTS, adversarial LLM state machine, dual-direction interruption manager, and composure scoring engine.
  - **Frontend (Built by Codex, Runs in Web Browser):** Web interface using browser Web Audio API (`getUserMedia`), audio playback, real-time pressure HUD, composure meters, transcript display, scenario switcher, and a **Custom Topic** input field!

---

## 2. Supported Debate Modes & Personas

The user can choose between 4 modes in the UI:
1. **The Skeptical Tier-1 VC (`vc_pitch`):**
   - Startup pitch grilling. Relentlessly challenges valuation, unit economics (CAC, LTV, payback), defensibility, and market size.
2. **The Hardball VP of Talent (`salary_negotiation`):**
   - High-stakes compensation negotiation. Counters aggressive salary demands, pushes back on equity, defends company bands.
3. **The Hostile Legal Prosecutor (`hostile_cross_exam`):**
   - Courtroom cross-examination. Pounces on inconsistencies, timeline gaps, and hesitations.
4. **Custom Freeform Debate Topic (`custom_debate`):**
   - **Any topic the user wants!** The user types or speaks a topic (e.g., *"AI will take everyone's jobs"*, *"Electric cars are bad"*, *"College degrees are useless"*).
   - The AI automatically assumes the sharp contrarian position against the user's stance and starts an intense, rapid-fire intellectual debate!

---

## 3. Browser Web Audio Integration (How Frontend Talks to Backend)

### A. Capturing Microphone in Browser (Client ➔ Server)
The browser UI records from the user's microphone using Web Audio API and streams 16kHz 16-bit linear PCM over the WebSocket:

```javascript
// Example standard Browser Web Audio capture for Codex:
const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } });
const audioCtx = new AudioContext({ sampleRate: 16000 });
const source = audioCtx.createMediaStreamSource(stream);
const processor = audioCtx.createScriptProcessor(4096, 1, 1);

processor.onaudioprocess = (e) => {
  const inputData = e.inputBuffer.getChannelData(0);
  // Convert Float32 to Int16 PCM
  const pcm16 = new Int16Array(inputData.length);
  for (let i = 0; i < inputData.length; i++) {
    pcm16[i] = Math.max(-1, Math.min(1, inputData[i])) * 0x7FFF;
  }
  // Send raw binary PCM frame to backend WebSocket
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(pcm16.buffer);
  }
};
source.connect(processor);
processor.connect(audioCtx.destination);
```

### B. Playing AI Spoken Voice in Browser (Server ➔ Client)
The backend sends streaming audio chunks from Rime. The browser plays them smoothly:
- If sent as binary PCM or base64 audio chunks: The browser pushes them to an `AudioContext` queue or `SourceBuffer`.
- On interruption event (`type: "interruption"`): The browser **immediately clears the audio playback queue** so sound stops instantly!

---

## 4. WebSocket API Contract (`/ws/debate`)

- **URL:** `ws://localhost:8000/ws/debate?scenario={scenario_id}&topic={custom_topic}&difficulty={level}`
  - `scenario`: `"vc_pitch"` | `"salary_negotiation"` | `"hostile_cross_exam"` | `"custom_debate"`
  - `topic`: URL-encoded custom topic string (e.g. `Why%20remote%20work%20is%20better`)
  - `difficulty`: `"easy"` | `"medium"` | `"hard"` | `"ruthless"` (default: `"hard"`)

### Server ➔ Client JSON Events

```json
// 1. Live Transcripts (AssemblyAI)
{
  "type": "transcript",
  "role": "user" | "ai",
  "text": "Our customer acquisition cost is... um, around fifty dollars...",
  "is_final": false,
  "confidence": 0.94
}

// 2. Interruption / Barge-in Event (Sub-100ms cut-off)
{
  "type": "interruption",
  "by": "user" | "ai",
  "latency_ms": 84,
  "reason": "user_barge_in" | "fluff_detected"
}

// 3. Live Composure & Speech Telemetry (AssemblyAI metrics)
{
  "type": "composure_telemetry",
  "composure_score": 74,
  "current_wpm": 168,
  "filler_word_count": 5,
  "recent_fillers": ["um", "like"],
  "hesitation_seconds": 1.8,
  "pressure_level": 3
}

// 4. AI Speaking State
{
  "type": "ai_state",
  "state": "listening" | "thinking" | "speaking" | "interrupted"
}

// 5. Post-Debate Debrief Report
{
  "type": "debate_report",
  "overall_score": 72,
  "verdict": "CHALLENGE SURVIVED",
  "metrics": { "avg_wpm": 154, "total_fillers": 9, "barge_ins": 3 },
  "key_weaknesses": ["Stammered during valuation defense"],
  "coaching_tips": ["Lead with concrete numbers before storytelling"]
}
```

---

## 5. UI Layout Blueprint for Codex

1. **Top Bar:**
   - Mode Selector: Tab buttons for `VC Pitch`, `Salary Negotiation`, `Hostile Cross-Exam`, and `Custom Debate`.
   - If `Custom Debate` is chosen: An input box appears: *"Enter any topic to debate (e.g., AI ethics, remote work, nuclear energy)..."*
   - Difficulty pills: `Easy`, `Medium`, `Hard`, `Ruthless`.
2. **Central Arena:**
   - **Adversary Visualizer:** Dynamic voice orb / wave that pulses when AI speaks, flashes red on aggressive counter-arguments, and ripples on barge-in.
   - **Split Transcript Stream:** User on left (with fillers highlighted in amber), AI on right (with critical pushbacks in red).
   - **Interruption Banner:** Real-time badge whenever user or AI interrupts (e.g. `⚡ Barge-in: 78ms cutoff`).
3. **Composure & Pressure HUD:**
   - **Composure Gauge (0-100)**: Real-time verbal stability meter.
   - **Speech Cadence (WPM)**: Speed gauge.
   - **Filler Word Tally**: Live counter of "um", "uh", "like", "basically".
   - **Pressure Barometer**: Level 1 to 5.
4. **Controls:**
   - Mic Toggle (Push-to-Talk or Open Mic).
   - "End Debate / Debrief" button.

---

## 6. How to Run Backend

```powershell
cd "D:\Voice AI\Application"
uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
```
- API Docs: `http://localhost:8000/docs`
- WebSocket: `ws://localhost:8000/ws/debate`
