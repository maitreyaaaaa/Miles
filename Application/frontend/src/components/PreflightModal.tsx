import React, { useEffect, useRef, useState } from "react";
import { CheckCircle2, Mic, Play, RefreshCw, ShieldCheck, Volume2, X, AlertTriangle } from "lucide-react";
import type { PreflightResponse } from "../types";

interface PreflightModalProps {
  isOpen: boolean;
  onClose: () => void;
  backendUrl: string;
}

export const PreflightModal: React.FC<PreflightModalProps> = ({ isOpen, onClose, backendUrl }) => {
  const [micActive, setMicActive] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [speakerTested, setSpeakerTested] = useState(false);
  const [preflightData, setPreflightData] = useState<PreflightResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const audioCtxRef = useRef<AudioContext | null>(null);
  const chimeCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number | null>(null);

  const fetchStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${backendUrl}/api/preflight`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as PreflightResponse;
      setPreflightData(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to probe backend");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    fetchStatus();

    // Start mic monitor
    let active = true;
    navigator.mediaDevices
      ?.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      .then((stream) => {
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
        audioCtxRef.current = ctx;
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);

        const data = new Uint8Array(analyser.frequencyBinCount);
        const updateRms = () => {
          if (!active) return;
          analyser.getByteTimeDomainData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) {
            const v = (data[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / data.length);
          setMicLevel(Math.min(100, Math.round(rms * 250)));
          if (rms > 0.03) setMicActive(true);
          animFrameRef.current = requestAnimationFrame(updateRms);
        };
        updateRms();
      })
      .catch((e) => console.warn("Mic preflight access error:", e));

    return () => {
      active = false;
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
      if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
        audioCtxRef.current.close().catch(() => {});
      }
      if (chimeCtxRef.current && chimeCtxRef.current.state !== "closed") {
        chimeCtxRef.current.close().catch(() => {});
        chimeCtxRef.current = null;
      }
    };
  }, [isOpen]);

  const playChime = () => {
    try {
      if (chimeCtxRef.current && chimeCtxRef.current.state !== "closed") {
        chimeCtxRef.current.close().catch(() => {});
        chimeCtxRef.current = null;
      }
      const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      chimeCtxRef.current = ctx;
      ctx.resume().then(() => {
        const now = ctx.currentTime;
        const osc1 = ctx.createOscillator();
        const gain1 = ctx.createGain();
        osc1.frequency.setValueAtTime(440, now);
        gain1.gain.setValueAtTime(0.2, now);
        gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
        osc1.connect(gain1);
        gain1.connect(ctx.destination);
        osc1.start(now);
        osc1.stop(now + 0.3);

        const osc2 = ctx.createOscillator();
        const gain2 = ctx.createGain();
        osc2.frequency.setValueAtTime(880, now + 0.25);
        gain2.gain.setValueAtTime(0.2, now + 0.25);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.6);
        osc2.connect(gain2);
        gain2.connect(ctx.destination);
        osc2.start(now + 0.25);
        osc2.stop(now + 0.6);

        osc2.onended = () => {
          if (chimeCtxRef.current === ctx) {
            ctx.close().catch(() => {});
            chimeCtxRef.current = null;
          }
        };
      });
    } catch (e) {
      console.warn("Chime playback error:", e);
    }
  };

  const handlePassAndClose = () => {
    sessionStorage.setItem("miles_preflight_passed", "true");
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in">
      <div className="relative w-full max-w-lg rounded-2xl border border-white/10 bg-[#0d0f12] p-6 shadow-2xl text-white">
        <div className="flex items-center justify-between pb-4 border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Voice Preflight Check</h2>
              <p className="text-xs text-white/50">Verify audio hardware & cloud inference pipelines</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-white/40 hover:bg-white/5 hover:text-white transition">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-5 space-y-4 text-sm">
          {/* Microphone Check */}
          <div className="flex flex-col gap-2 rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Mic className="h-4 w-4 text-emerald-400" />
                <span className="font-medium">Microphone Input</span>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full font-mono ${micActive ? "bg-emerald-500/20 text-emerald-400" : "bg-white/5 text-white/40"}`}>
                {micActive ? "Signal OK" : "Speak to test"}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full bg-emerald-500 transition-all duration-75"
                style={{ width: `${Math.max(5, micLevel)}%` }}
              />
            </div>
          </div>

          {/* Speaker Check */}
          <div className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
            <div className="flex items-center gap-2.5">
              <Volume2 className="h-4 w-4 text-emerald-400" />
              <div>
                <div className="font-medium">Speaker Output</div>
                <div className="text-xs text-white/40">Plays 440Hz / 880Hz dual-tone chime</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={playChime}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-xs hover:bg-white/10 transition"
              >
                <Play className="h-3 w-3" /> Play
              </button>
              <button
                onClick={() => setSpeakerTested(true)}
                className={`rounded-lg px-2.5 py-1 text-xs transition ${
                  speakerTested ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "border border-white/10 bg-white/5 hover:bg-white/10"
                }`}
              >
                {speakerTested ? "✓ Confirmed" : "I heard it"}
              </button>
            </div>
          </div>

          {/* Cloud Health Diagnostics */}
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5 space-y-2">
            <div className="flex items-center justify-between text-xs text-white/50 mb-1">
              <span>Cloud Engine Pipeline</span>
              <button onClick={fetchStatus} disabled={loading} className="hover:text-white flex items-center gap-1">
                <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Refresh
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="flex items-center justify-between rounded bg-white/[0.03] px-2.5 py-1.5">
                <span className="text-white/60">Backend:</span>
                <span className="text-emerald-400 font-semibold">{preflightData?.backend_status || "Checking..."}</span>
              </div>
              <div className="flex items-center justify-between rounded bg-white/[0.03] px-2.5 py-1.5">
                <span className="text-white/60">AssemblyAI v3:</span>
                <span className={preflightData?.assemblyai_status === "connected" ? "text-emerald-400" : "text-amber-400"}>
                  {preflightData?.assemblyai_status || "Checking..."}
                </span>
              </div>
              <div className="flex items-center justify-between rounded bg-white/[0.03] px-2.5 py-1.5">
                <span className="text-white/60">Rime Coda:</span>
                <span className={preflightData?.rime_status === "connected" ? "text-emerald-400" : "text-amber-400"}>
                  {preflightData?.rime_status || "Checking..."}
                </span>
              </div>
              <div className="flex items-center justify-between rounded bg-white/[0.03] px-2.5 py-1.5">
                <span className="text-white/60">Active LLM:</span>
                <span className="text-white/80 truncate max-w-[90px]">{preflightData?.active_llm?.split("/").pop() || "Llama 3.3"}</span>
              </div>
            </div>
            {error && (
              <div className="flex items-center gap-2 text-xs text-rose-400 bg-rose-500/10 p-2 rounded">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </div>
        </div>

        <div className="mt-6 flex items-center justify-between pt-4 border-t border-white/10">
          <button
            onClick={handlePassAndClose}
            className="text-xs text-white/40 hover:text-white/80 transition"
          >
            Skip &amp; Start
          </button>
          <button
            onClick={handlePassAndClose}
            className="flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-2 text-sm font-semibold text-black hover:bg-emerald-400 shadow-lg shadow-emerald-500/20 transition"
          >
            <CheckCircle2 className="h-4 w-4" /> Start Sparring Session
          </button>
        </div>
      </div>
    </div>
  );
};
