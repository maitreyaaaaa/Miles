import React, { useEffect, useRef, useState } from "react";
import { CheckCircle2, Mic, Play, ShieldCheck, Volume2, X } from "lucide-react";
import { useAccessibleDialog } from "../hooks/useAccessibleDialog";
import { apiFetch, BACKEND_URL } from "../api";
import type { PreflightResponse } from "../types";

interface PreflightModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm?: () => void;
  backendUrl?: string;
}

export const PreflightModal: React.FC<PreflightModalProps> = ({ isOpen, onClose, onConfirm, backendUrl = BACKEND_URL }) => {
  const [micActive, setMicActive] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [speakerTested, setSpeakerTested] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const [services, setServices] = useState<"checking" | "ready" | "unavailable">("checking");
  const [serviceAttempt, setServiceAttempt] = useState(0);
  const [serviceError, setServiceError] = useState("");
  useEffect(() => {
    if (!isOpen) return;
    const controller = new AbortController();
    let active = true;
    const timer = window.setTimeout(() => controller.abort(), 16_000);
    setServices("checking");
    setServiceError("");
    void (async () => {
      try {
        const response = await apiFetch(`${backendUrl}/api/preflight`, { signal: controller.signal });
        if (!response.ok) throw new Error("Voice setup could not be checked. Please try again.");
        const data = await response.json() as PreflightResponse;
        if (!data.voice_ready) throw new Error("Voice practice is temporarily unavailable. Please try again shortly.");
        if (active) setServices("ready");
      } catch (error) {
        if (active) {
          setServices("unavailable");
          setServiceError(controller.signal.aborted ? "Voice setup took too long. Check your connection and retry." : error instanceof Error ? error.message : "Voice setup failed.");
        }
      } finally { window.clearTimeout(timer); }
    })();
    return () => { active = false; controller.abort(); window.clearTimeout(timer); };
  }, [isOpen, backendUrl, serviceAttempt]);

  const audioCtxRef = useRef<AudioContext | null>(null);
  const chimeCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const dialogRef = useAccessibleDialog<HTMLDivElement>(isOpen, onClose);

  useEffect(() => {
    if (!isOpen) return;

    // Start mic monitor
    let active = true;
    setMicActive(false);
    setMicLevel(0);
    setSpeakerTested(false);
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicError("Microphone testing is not supported by this browser.");
      return;
    }
    setMicError(null);
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      .then((stream) => {
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
        audioCtxRef.current = ctx;
        void ctx.resume().catch(() => setMicError("Click the audio setup controls to enable your microphone in this browser."));
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
      .catch((e) => {
        setMicError(e instanceof Error && e.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow microphone access to use voice sparring."
          : "The microphone could not be started. Check your browser and device settings.");
        console.warn("Mic preflight access error:", e);
      });

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
      // Resume microphone analysis in this user gesture for stricter autoplay policies.
      void audioCtxRef.current?.resume().catch(() => setMicError("Your microphone could not be enabled. Check browser audio permissions."));
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
    if (!micActive || !speakerTested || services !== "ready") return;
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
        ref={dialogRef}
        className="preflight-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="preflight-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="preflight-header">
          <div className="preflight-title-wrap">
            <div className="preflight-icon-badge">
              <ShieldCheck size={20} />
            </div>
            <div className="preflight-titles">
              <h2 id="preflight-title">Audio &amp; Voice Setup</h2>
              <p>Check your microphone, headphones, and voice connection</p>
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
          <div className="preflight-check-card" aria-live="polite">
            <div className="preflight-row">
              <div className="preflight-item-left"><ShieldCheck size={18} /><div>
                <div className="preflight-item-label">Voice connection</div>
                <div className="preflight-item-sub">{services === "checking" ? "Checking speech, voice, and conversation services…" : services === "ready" ? "Ready for your round" : "Connection needs attention"}</div>
              </div></div>
              {services === "unavailable" && <button type="button" className="preflight-action-pill" onClick={() => setServiceAttempt((value) => value + 1)}>Retry</button>}
            </div>
            {serviceError && <p className="session-error-banner" role="alert">{serviceError}</p>}
          </div>
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
              <span className={`preflight-status-badge ${micActive ? "active" : ""}`} role={micError ? "alert" : "status"}>
                {micError || (micActive ? "Signal Detected" : "Speak to test")}
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
            onClick={onClose}
            className="preflight-skip-btn"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handlePassAndClose}
            className="preflight-submit-btn"
            disabled={!micActive || !speakerTested || services !== "ready"}
          >
            <CheckCircle2 size={16} /> Start practice
          </button>
        </div>
      </div>
    </div>
  );
};
