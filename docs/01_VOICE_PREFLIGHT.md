# Feature Specification: Voice Preflight Screen

## 1. Problem Statement
In live voice agent demonstrations, the most catastrophic failure modes stem from silent client-side audio hardware and networking mismatches:
- Microphone permissions blocked or mapped to an unplugged input device.
- System volume muted or headphones inactive, leading the user or judge to conclude the AI is broken ("I can't hear anything").
- Autoplay audio context suppressed by modern browser security policies until a deliberate user gesture occurs.
- WebSocket handshake blocked by network firewall or server downtime.

## 2. Solution Overview
Before any sparring round starts, Miles displays an unobtrusive, elegant **Voice Preflight Modal**. It executes an end-to-end hardware and connection diagnostic in under 3 seconds. Once passed, the session caches the confirmation so subsequent runs can jump straight into battle.

---

## 3. Diagnostic Checkpoints

| Checkpoint | Verification Method | Pass Condition | Fallback Action |
| :--- | :--- | :--- | :--- |
| **Microphone Input** | Web Audio `getUserMedia` + RMS analyzer | Detected live acoustic signal (RMS > 0.05) | Displays browser permission prompt with browser-specific instructions |
| **Speaker Output** | Web Audio dual-tone chime playback | User confirms audible chime via 1-click prompt | Plays synthesized chime buffer and resumes audio context |
| **Backend Connection** | WebSocket ping to `/ws/debate` | Handshake acknowledged within <50ms | Displays clear offline error & retry button |
| **AssemblyAI v3 Engine**| Ephemeral streaming token retrieval | Valid token fetched from `/api/stt/token` | Warns if offline simulation STT fallback active |
| **Rime Neural TTS** | Status probe on `coda` / `mistv3` | Connection pool warmed & responsive (<250ms) | Switches gracefully to local speech synthesizer |

---

## 4. Technical Architecture

### Frontend Layer (`frontend/src/components/PreflightModal.tsx`)
1. **AudioContext Initialization**: Creates an `AudioContext` at 16kHz for mic linear PCM and 22.05kHz for speaker audio. Calling `.resume()` here permanently unlocks autoplay audio for the entire session.
2. **Real-Time Visualizer**: An HTML5 `<canvas>` or CSS animated VU-meter visualizes inbound audio level in real time.
3. **Sound Chime Test**: Plays a pleasant 440Hz/880Hz two-tone chime (`AudioBufferSourceNode`) with a prominent "I Heard It" button.
4. **Session Storage Bypass**:
   ```typescript
   sessionStorage.setItem('miles_preflight_passed', 'true');
   ```

### Backend Layer (`src/api/server.py`)
- Endpoint: `GET /api/preflight`
- Response:
  ```json
  {
    "backend_status": "healthy",
    "assemblyai_status": "connected",
    "assemblyai_model": "universal-3-5-pro",
    "rime_status": "connected",
    "rime_model": "coda",
    "rime_speaker": "alpine",
    "active_llm": "meta-llama/llama-3.3-70b-instruct"
  }
  ```

---

## 5. UI Layout & Wireframe

```
┌────────────────────────────────────────────────────────┐
│                   MILES VOICE PREFLIGHT                │
│       Calibrating audio environment for live sparring   │
├────────────────────────────────────────────────────────┤
│                                                        │
│  [✓] Microphone Input                                  │
│      Default - Realtek High Definition Audio           │
│      Level: [██████████░░░░░░] Speaking detected       │
│                                                        │
│  [✓] Speaker Output                                    │
│      [ ▶ Play Test Chime ]  Did you hear it? [ Yes ]   │
│                                                        │
│  [✓] Backend Full-Duplex Server                        │
│      ws://localhost:8000/ws/debate (14ms ping)         │
│                                                        │
│  [✓] AssemblyAI Universal-Streaming v3                 │
│      Token acquired • Sub-200ms acoustic pipeline     │
│                                                        │
│  [✓] Rime Neural TTS Engine                            │
│      Model: Coda • Speaker: Alpine • Pool: Warm        │
│                                                        │
├────────────────────────────────────────────────────────┤
│  [ Start Sparring Session ]    [ Don't show again ]    │
└────────────────────────────────────────────────────────┘
```
