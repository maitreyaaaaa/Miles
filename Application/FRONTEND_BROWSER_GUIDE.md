# FRONTEND_BROWSER_GUIDE.md — Codex Integration Guide for Web Browser

> **For Codex / Web Developer**: This guide contains ready-to-use JavaScript/TypeScript snippets for integrating your browser UI with the **Miles** backend via WebSocket & Web Audio API.

---

## 1. WebSocket Endpoint & Parameters

Connect to:
```
ws://localhost:8000/ws/debate?scenario={SCENARIO_ID}&topic={CUSTOM_TOPIC}&difficulty={LEVEL}
```

| Parameter | Type | Default | Options / Examples |
|---|---|---|---|
| `scenario` | string | `vc_pitch` | `vc_pitch`, `salary_negotiation`, `hostile_cross_exam`, `custom_debate` |
| `topic` | string | None | URL-encoded custom topic (e.g. `Electric%20Vehicles%20are%20overrated`) |
| `difficulty` | string | `hard` | `easy`, `medium`, `hard`, `ruthless` |

---

## 2. Inbound: Microphone Capture (Browser ➔ Backend)

The backend expects **16kHz, 16-bit linear PCM mono** binary frames. Here is the modern browser implementation:

```javascript
let audioContext = null;
let mediaStream = null;
let scriptProcessor = null;

async function startMicrophoneCapture(websocket) {
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate: 16000,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  const source = audioContext.createMediaStreamSource(mediaStream);
  
  // 4096 samples = ~256ms chunk at 16kHz
  scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);

  scriptProcessor.onaudioprocess = (e) => {
    if (websocket.readyState !== WebSocket.OPEN) return;

    const inputData = e.inputBuffer.getChannelData(0);
    // Convert Float32 [-1.0, 1.0] to Int16 PCM [-32768, 32767]
    const pcm16 = new Int16Array(inputData.length);
    for (let i = 0; i < inputData.length; i++) {
      const s = Math.max(-1, Math.min(1, inputData[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Send binary PCM frame directly to backend
    websocket.send(pcm16.buffer);
  };

  source.connect(scriptProcessor);
  scriptProcessor.connect(audioContext.destination);
}

function stopMicrophoneCapture() {
  if (scriptProcessor) scriptProcessor.disconnect();
  if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop());
  if (audioContext) audioContext.close();
}
```

---

## 3. Outbound: Ultra-Low Latency Audio Player (Backend ➔ Browser)

The backend streams 22,050Hz neural TTS audio chunks. To achieve instant **Sub-100ms Barge-in Cut-off**, maintain an active queue of scheduled `AudioBufferSourceNode`s. When an `interruption` event is received, abort them immediately!

```javascript
class VoicePlayer {
  constructor(sampleRate = 22050) {
    this.sampleRate = sampleRate;
    this.audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate });
    this.activeNodes = [];
    this.nextStartTime = 0;
  }

  // Play incoming raw PCM binary chunk
  playChunk(arrayBuffer) {
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }

    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    const buffer = this.audioCtx.createBuffer(1, float32Array.length, this.sampleRate);
    buffer.copyToChannel(float32Array, 0);

    const source = this.audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.audioCtx.destination);

    const now = this.audioCtx.currentTime;
    const startTime = Math.max(now, this.nextStartTime);
    source.start(startTime);
    this.nextStartTime = startTime + buffer.duration;

    this.activeNodes.push(source);
    source.onended = () => {
      const idx = this.activeNodes.indexOf(source);
      if (idx !== -1) this.activeNodes.splice(idx, 1);
    };
  }

  // CRUCIAL: Instant Barge-in Audio Purge!
  stopImmediately() {
    this.activeNodes.forEach((node) => {
      try {
        node.stop();
        node.disconnect();
      } catch (e) {}
    });
    this.activeNodes = [];
    this.nextStartTime = 0;
  }
}
```

---

## 4. Handling Backend WebSocket Events

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/debate?scenario=vc_pitch&difficulty=hard");
ws.binaryType = "arraybuffer";
const player = new VoicePlayer(22050);

ws.onmessage = (event) => {
  // 1. Binary Audio Frame from Rime TTS
  if (event.data instanceof ArrayBuffer) {
    player.playChunk(event.data);
    return;
  }

  // 2. JSON Event
  const msg = JSON.parse(event.data);
  switch (msg.type) {
    case "transcript":
      // { role: "user" | "ai", text: "...", is_final: boolean, confidence: number }
      updateTranscriptUI(msg.role, msg.text, msg.is_final);
      break;

    case "interruption":
      // { by: "user" | "ai", latency_ms: 0.05, reason: "user_barge_in" | "fluff_detected" }
      player.stopImmediately(); // INSTANT SILENCE!
      showInterruptionBanner(msg.by, msg.latency_ms);
      break;

    case "composure_telemetry":
      // { composure_score: 78, current_wpm: 152, filler_word_count: 3, pressure_level: 4 }
      updateComposureMeter(msg.composure_score);
      updateWpmGauge(msg.current_wpm);
      updateFillerTally(msg.filler_word_count, msg.recent_fillers);
      updatePressureBar(msg.pressure_level);
      break;

    case "ai_state":
      // "listening" | "thinking" | "speaking" | "interrupted"
      updateAdversaryVisualizer(msg.state);
      break;

    case "debate_report":
      // Final debrief report
      renderDebriefModal(msg);
      break;
  }
};
```

---

## 5. UI Layout Recommendations
- **Composure Gauge**: Circular or horizontal bar showing 0–100 with color gradient (Red < 50, Yellow 50–75, Green 75–100).
- **Adversary Visualizer**: Pulsing voice orb that is electric blue when listening, purple when thinking, deep fiery crimson when speaking adversarial traps, and ripples instantly on barge-in.
- **Transcript Split**: User responses on the left (highlighting filler words in yellow), Adversary counters on the right.
