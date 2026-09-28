import { VoicePlayer } from "./audio";

const statusText = document.querySelector<HTMLElement>("#status");
const setStatus = (message: string) => {
  if (statusText) statusText.textContent = message;
};

const params = new URLSearchParams(window.location.search);
const ticket = params.get("ticket");
if (!ticket) {
  setStatus("This meeting link is invalid.");
  throw new Error("Missing meeting audio bridge ticket.");
}

// The ticket is a bearer capability; remove it from the visible URL and history once read.
window.history.replaceState(null, "", window.location.pathname);

const backendUrl = new URL(import.meta.env.VITE_BACKEND_URL || window.location.origin);
backendUrl.protocol = backendUrl.protocol === "https:" ? "wss:" : "ws:";
backendUrl.pathname = `${backendUrl.pathname.replace(/\/$/, "")}/ws/debate`;
backendUrl.search = "?meeting_bridge=true&audio_format=binary";

const socket = new WebSocket(backendUrl);
socket.binaryType = "arraybuffer";
const player = new VoicePlayer(22050);
let mediaStream: MediaStream | null = null;
let inputContext: AudioContext | null = null;
let processor: ScriptProcessorNode | null = null;
let inputSource: MediaStreamAudioSourceNode | null = null;
let mutedOutput: GainNode | null = null;
let bridgeActive = false;
let terminalMessage = "";

function toPcm16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index]));
    output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

function resampleTo16k(input: Float32Array, sampleRate: number): Int16Array {
  if (sampleRate === 16000) return toPcm16(input);
  const outputLength = Math.floor((input.length * 16000) / sampleRate);
  const output = new Int16Array(outputLength);
  const step = sampleRate / 16000;
  for (let index = 0; index < outputLength; index += 1) {
    const position = index * step;
    const left = Math.floor(position);
    const fraction = position - left;
    const sample = input[left] * (1 - fraction) + (input[Math.min(left + 1, input.length - 1)] ?? 0) * fraction;
    const clipped = Math.max(-1, Math.min(1, sample));
    output[index] = clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff;
  }
  return output;
}

async function startMeetingAudio() {
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    },
  });
  inputContext = new AudioContext({ sampleRate: 16000 });
  await inputContext.resume();
  inputSource = inputContext.createMediaStreamSource(mediaStream);
  processor = inputContext.createScriptProcessor(1024, 1, 1);
  mutedOutput = inputContext.createGain();
  mutedOutput.gain.value = 0;

  processor.onaudioprocess = (event) => {
    if (!bridgeActive || socket.readyState !== WebSocket.OPEN) return;
    const pcm = resampleTo16k(event.inputBuffer.getChannelData(0), inputContext?.sampleRate ?? 16000);
    if (pcm.length > 0) socket.send(pcm.buffer);
  };

  // ScriptProcessorNode must connect to a destination to run. Keep monitor output silent
  // so meeting audio is not echoed back into the call; only VoicePlayer is audible to Recall.
  inputSource.connect(processor);
  processor.connect(mutedOutput);
  mutedOutput.connect(inputContext.destination);
  await player.ensureRunning();
  socket.send(JSON.stringify({ type: "meeting_bridge_audio_ready" }));
}

function stopAudio() {
  processor?.disconnect();
  inputSource?.disconnect();
  mutedOutput?.disconnect();
  mediaStream?.getTracks().forEach((track) => track.stop());
  if (inputContext && inputContext.state !== "closed") void inputContext.close();
  void player.close();
}

socket.addEventListener("open", () => {
  socket.send(JSON.stringify({ type: "meeting_bridge_auth", ticket }));
  setStatus("Connecting to Miles…");
});

socket.addEventListener("message", (event: MessageEvent<ArrayBuffer | string>) => {
  if (event.data instanceof ArrayBuffer) {
    void player.playChunk(event.data);
    return;
  }
  try {
    const message = JSON.parse(event.data);
    if (message.type === "ai_state") {
      setStatus(message.state === "speaking" ? "Miles is responding…" : "Listening and ready to respond.");
    } else if (message.type === "meeting_bridge_ready") {
      setStatus("Connecting meeting audio…");
      void startMeetingAudio().catch((error: unknown) => {
        console.error("Could not start Recall meeting audio.", error);
        setStatus("Audio could not start. Miles disconnected.");
        socket.close(1011, "Meeting audio unavailable");
      });
    } else if (message.type === "meeting_bridge_started") {
      bridgeActive = true;
      setStatus("Listening and ready to respond.");
    } else if (message.type === "meeting_bridge_error") {
      terminalMessage = typeof message.message === "string" ? message.message : "Miles could not start.";
      setStatus(terminalMessage);
    } else if (message.type === "debrief_status") {
      setStatus("Finishing the meeting debrief…");
    }
  } catch {
    // Ignore non-JSON text frames; audio continues independently.
  }
});

socket.addEventListener("close", () => {
  stopAudio();
  setStatus(terminalMessage || "Meeting connection ended.");
});

socket.addEventListener("error", () => {
  setStatus("Connection interrupted.");
});

window.addEventListener("pagehide", () => {
  if (socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "end_debate" }));
  }
  stopAudio();
  socket.close();
});
