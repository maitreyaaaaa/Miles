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
    <div className="preflight-overlay" role="presentation" onClick={onClose}>
      <div
        className="preflight-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Voice Preflight Check"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="preflight-header">
          <div className="preflight-title-wrap">
            <div className="preflight-icon-badge">
              <ShieldCheck size={20} />
            </div>
            <div className="preflight-titles">
              <h2>Voice Preflight Check</h2>
              <p>Verify audio hardware &amp; cloud inference pipelines</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="preflight-close-btn"
            title="Close modal"
          >
            <X size={16} />
          </button>
        </div>

        <div className="preflight-body">
          {/* Microphone Check */}
          <div className="preflight-check-card">
            <div className="preflight-row">
              <div className="preflight-item-left">
                <Mic size={18} className="preflight-item-icon" />
                <div>
                  <div className="preflight-item-label">Microphone Input</div>
                  <div className="preflight-item-sub">Speak to calibrate input sensitivity</div>
                </div>
              </div>
              <span className={`preflight-status-badge ${micActive ? "active" : ""}`}>
                {micActive ? "Signal OK" : "Speak to test"}
              </span>
            </div>
            <div className="preflight-meter-track">
              <div
                className="preflight-meter-fill"
                style={{ width: `${Math.max(5, micLevel)}%` }}
              />
            </div>
          </div>

          {/* Speaker Check */}
          <div className="preflight-check-card">
            <div className="preflight-row">
              <div className="preflight-item-left">
                <Volume2 size={18} className="preflight-item-icon" />
                <div>
                  <div className="preflight-item-label">Speaker Output</div>
                  <div className="preflight-item-sub">Plays 440Hz / 880Hz dual-tone chime</div>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <button
                  type="button"
                  onClick={playChime}
                  className="preflight-action-pill"
                >
                  <Play size={12} /> Play
                </button>
                <button
                  type="button"
                  onClick={() => setSpeakerTested(true)}
                  className={`preflight-action-pill ${speakerTested ? "confirmed" : ""}`}
                >
                  {speakerTested ? "✓ Confirmed" : "I heard it"}
                </button>
              </div>
            </div>
          </div>

          {/* Cloud Health Diagnostics */}
          <div className="preflight-check-card">
            <div className="preflight-row" style={{ marginBottom: "2px" }}>
              <span className="preflight-item-sub" style={{ textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
                Cloud Engine Pipeline
              </span>
              <button
                type="button"
                onClick={fetchStatus}
                disabled={loading}
                className="preflight-refresh-btn"
                title="Re-probe cloud services"
              >
                <RefreshCw size={12} className={loading ? "spin-icon" : ""} /> Refresh
              </button>
            </div>
            <div className="preflight-grid">
              <div className="preflight-grid-cell">
                <span className="preflight-cell-label">Backend:</span>
                <span className={`preflight-cell-val ${preflightData?.backend_status === "healthy" ? "healthy" : ""}`}>
                  {preflightData?.backend_status || "Checking..."}
                </span>
              </div>
              <div className="preflight-grid-cell">
                <span className="preflight-cell-label">AssemblyAI v3:</span>
                <span className={`preflight-cell-val ${preflightData?.assemblyai_status === "connected" ? "connected" : "warning"}`}>
                  {preflightData?.assemblyai_status || "Checking..."}
                </span>
              </div>
              <div className="preflight-grid-cell">
                <span className="preflight-cell-label">Rime Coda:</span>
                <span className={`preflight-cell-val ${preflightData?.rime_status === "connected" ? "connected" : "warning"}`}>
                  {preflightData?.rime_status || "Checking..."}
                </span>
              </div>
              <div className="preflight-grid-cell">
                <span className="preflight-cell-label">Active LLM:</span>
                <span className="preflight-cell-val truncate">
                  {preflightData?.active_llm?.split("/").pop() || "Llama 3.3"}
                </span>
              </div>
            </div>
            {error && (
              <div className="preflight-error-banner">
                <AlertTriangle size={14} style={{ flexShrink: 0 }} />
                <span>{error}</span>
              </div>
            )}
          </div>
        </div>

        <div className="preflight-footer">
          <button
            type="button"
            onClick={handlePassAndClose}
            className="preflight-skip-btn"
          >
            Skip &amp; Start
          </button>
          <button
            type="button"
            onClick={handlePassAndClose}
            className="preflight-submit-btn"
          >
            <CheckCircle2 size={16} /> Start Sparring Session
          </button>
        </div>
      </div>
    </div>
  );
};
