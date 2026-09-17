import React, { useEffect, useRef, useState } from "react";
import { CheckCircle2, Mic, Play, ShieldCheck, Volume2, X } from "lucide-react";

interface PreflightModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm?: () => void;
  backendUrl?: string;
}

export const PreflightModal: React.FC<PreflightModalProps> = ({ isOpen, onClose, onConfirm }) => {
  const [micActive, setMicActive] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [speakerTested, setSpeakerTested] = useState(false);

  const audioCtxRef = useRef<AudioContext | null>(null);
  const chimeCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isOpen) return;

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
    if (onConfirm) {
      onConfirm();
    } else {
      onClose();
    }
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
              <h2>Audio &amp; Voice Setup</h2>
              <p>Calibrate microphone input &amp; verify audio playback</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="preflight-close-btn"
            title="Close modal"
            aria-label="Close audio setup"
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
                  <div className="preflight-item-sub">Speak to test microphone sensitivity</div>
                </div>
              </div>
              <span className={`preflight-status-badge ${micActive ? "active" : ""}`}>
                {micActive ? "Signal Detected" : "Speak to test"}
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
                  <div className="preflight-item-label">Audio Playback</div>
                  <div className="preflight-item-sub">Plays 440Hz / 880Hz test chime</div>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <button
                  type="button"
                  onClick={playChime}
                  className="preflight-action-pill"
                >
                  <Play size={12} /> Play Chime
                </button>
                <button
                  type="button"
                  onClick={() => setSpeakerTested(true)}
                  className={`preflight-action-pill ${speakerTested ? "confirmed" : ""}`}
                >
                  {speakerTested ? "✓ Verified" : "I can hear it"}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="preflight-footer">
          <button
            type="button"
            onClick={handlePassAndClose}
            className="preflight-skip-btn"
          >
            Skip Setup
          </button>
          <button
            type="button"
            onClick={handlePassAndClose}
            className="preflight-submit-btn"
          >
            <CheckCircle2 size={16} /> Enter Sparring
          </button>
        </div>
      </div>
    </div>
  );
};
