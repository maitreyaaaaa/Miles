export class VoicePlayer {
  private audioCtx: AudioContext;
  private activeNodes: AudioBufferSourceNode[] = [];
  private nextStartTime = 0;

  constructor(private readonly sampleRate = 22050) {
    this.audioCtx = new AudioContext({ sampleRate });
  }

  async ensureRunning() {
    if (this.audioCtx.state === "suspended") {
      await this.audioCtx.resume();
    }
  }

  async unlock() {
    await this.ensureRunning();

    const buffer = this.audioCtx.createBuffer(1, 1, this.sampleRate);
    const source = this.audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.audioCtx.destination);
    source.start();
  }

  async playChunk(arrayBuffer: ArrayBuffer) {
    await this.ensureRunning();
    const byteLength = arrayBuffer.byteLength - (arrayBuffer.byteLength % 2);
    if (byteLength === 0) return;
    const int16Array = new Int16Array(arrayBuffer, 0, byteLength / 2);

    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i += 1) {
      float32Array[i] = int16Array[i] / 32768;
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
      this.activeNodes = this.activeNodes.filter((node) => node !== source);
    };
  }

  async playBase64Chunk(data: string) {
    const raw = window.atob(data);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) {
      bytes[i] = raw.charCodeAt(i);
    }
    await this.playChunk(bytes.buffer);
  }

  stopImmediately() {
    for (const node of this.activeNodes) {
      try {
        node.stop();
        node.disconnect();
      } catch {
        // Source nodes may already have ended.
      }
    }
    this.activeNodes = [];
    this.nextStartTime = 0;
  }

  async close() {
    this.stopImmediately();
    if (this.audioCtx.state !== "closed") {
      await this.audioCtx.close();
    }
  }
}

export class MicrophoneStreamer {
  private mediaStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;

  async start(websocket: WebSocket, onLevel: (level: number) => void) {
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    this.audioContext = new AudioContext({ sampleRate: 16000 });
    this.source = this.audioContext.createMediaStreamSource(this.mediaStream);
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);

    this.processor.onaudioprocess = (event) => {
      if (websocket.readyState !== WebSocket.OPEN) return;
      const inputData = event.inputBuffer.getChannelData(0);
      const pcm16 = new Int16Array(inputData.length);
      let sumSquares = 0;

      for (let i = 0; i < inputData.length; i += 1) {
        const sample = Math.max(-1, Math.min(1, inputData[i]));
        pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        sumSquares += sample * sample;
      }

      const rms = Math.sqrt(sumSquares / inputData.length);
      onLevel(Math.min(1, rms * 18));
      websocket.send(pcm16.buffer);
    };

    this.source.connect(this.processor);
    this.processor.connect(this.audioContext.destination);
  }

  stop() {
    if (this.processor) {
      this.processor.disconnect();
      this.processor.onaudioprocess = null;
    }
    if (this.source) this.source.disconnect();
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
    }
    if (this.audioContext && this.audioContext.state !== "closed") {
      void this.audioContext.close();
    }

    this.mediaStream = null;
    this.audioContext = null;
    this.processor = null;
    this.source = null;
  }
}
