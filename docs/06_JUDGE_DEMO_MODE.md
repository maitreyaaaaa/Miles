# Feature Specification: Hidden Demo Evidence Mode (`?demo=1`)

## 1. Problem Statement
During hackathon demos and judge evaluations:
- Judges want **hard technical evidence** that Miles is truly full-duplex, streaming, and sub-100ms.
- Standard users, however, should have a clean, cinematic interface with zero clutter.

## 2. Solution: Hidden Diagnostic HUD
Add a discrete **Demo Evidence HUD** activated via:
- URL parameter: `http://localhost:5173/?demo=1`
- Keyboard shortcut: `Ctrl + Shift + D` or `~` (backtick)

When active, a semi-transparent HUD drawer slides in from the right edge of the screen, revealing real-time telemetry, benchmarks, and event streams.

---

## 3. Demo HUD Layout & Panels

```
┌────────────────────────────────────────────────────────┐
│ [●] MILES REAL-TIME TELEMETRY (JUDGE DEMO MODE)    [×] │
├────────────────────────────────────────────────────────┤
│ SYSTEM HEALTH:                                         │
│ • AssemblyAI v3 WebSocket  : [ ONLINE ] 18ms ping      │
│ • Rime Neural Engine (Coda): [ ONLINE ] Pool warm      │
│ • Active LLM Provider      : OpenRouter / Llama 3.3 70B│
│ • Audio Context Status     : 16kHz In / 22.05kHz Out   │
├────────────────────────────────────────────────────────┤
│ LATENCY BENCHMARKS (LAST TURN):                        │
│ • Time-to-First-Audio (TTFA) : 894 ms  [EXCELLENT]     │
│ • Barge-in Cut-off Latency   : 0.018 ms [<100ms Target]│
│ • AssemblyAI Partial Delay   : 142 ms                  │
│ • LLM Time-to-First-Token    : 680 ms                  │
├────────────────────────────────────────────────────────┤
│ LIVE EVENT STREAM (CHRONOLOGICAL):                     │
│ [16:45:12.102] STT_PARTIAL: "our customer" (conf: 0.94)│
│ [16:45:12.450] STT_FINAL: "our customer acquisition"   │
│ [16:45:12.452] AI_TURN_TRIGGER: pipelined streaming    │
│ [16:45:13.132] FIRST_AUDIO_CHUNK: 22050Hz PCM base64   │
│ [16:45:14.201] BARGE_IN_TRIGGER: user speech RMS > 550 │
│ [16:45:14.202] RIME_STREAM_ABORT: aborted in 0.018ms   │
├────────────────────────────────────────────────────────┤
│ [ Copy Benchmarks to Clipboard ] [ Reset Session Log ] │
└────────────────────────────────────────────────────────┘
```

---

## 4. Technical Implementation

### Frontend Hook (`frontend/src/hooks/useDemoMode.ts`):
```typescript
export function useDemoMode() {
  const [isDemo, setIsDemo] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('demo') === '1';
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey && e.shiftKey && e.key === 'D') || e.key === '`') {
        setIsDemo((prev) => !prev);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return isDemo;
}
```

### Backend Metrics Emission:
Every WebSocket turn emits timing headers in events:
```json
{
  "type": "turn_telemetry",
  "ttfa_ms": 894.2,
  "barge_in_latency_ms": 0.018,
  "stt_provider": "AssemblyAI v3 (universal-3-5-pro)",
  "tts_provider": "Rime Coda (alpine)",
  "llm_provider": "meta-llama/llama-3.3-70b-instruct"
}
```
