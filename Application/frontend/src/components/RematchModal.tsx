import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Flame,
  Mic,
  MicOff,
  RotateCcw,
  Sparkles,
  Trophy,
  Volume2,
  X,
  Zap,
} from "lucide-react";
import type { RematchConfig, RematchEvaluationResult } from "../types";

declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

interface RematchModalProps {
  isOpen: boolean;
  config: RematchConfig | null;
  backendUrl?: string;
  onClose: () => void;
  onUpgradeAccepted?: (config: RematchConfig, result: RematchEvaluationResult) => void;
}

type RematchStage = "adversary_salvo" | "user_retry" | "evaluating" | "victory_summary";

const CANONICAL_FILLERS = [
  "um", "uh", "umm", "uhh", "ah", "er", "hmm", "like", "basically",
  "actually", "literally", "sort of", "kind of", "you know", "i mean",
];

export const RematchModal: React.FC<RematchModalProps> = ({
  isOpen,
  config,
  backendUrl = "http://localhost:8000",
  onClose,
  onUpgradeAccepted,
}) => {
  const [stage, setStage] = useState<RematchStage>("adversary_salvo");
  const [timeLeft, setTimeLeft] = useState<number>(30.0);
  const [userText, setUserText] = useState<string>("");
  const [isMicListening, setIsMicListening] = useState<boolean>(false);
  const [isAdversaryPlaying, setIsAdversaryPlaying] = useState<boolean>(false);
  const [evaluation, setEvaluation] = useState<RematchEvaluationResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const recognitionRef = useRef<any>(null);
  const timerIntervalRef = useRef<number | null>(null);

  const stopAudio = useCallback(() => {
    if (activeAudioRef.current) {
      try {
        activeAudioRef.current.pause();
        activeAudioRef.current.currentTime = 0;
      } catch {
        // Ignored
      }
      activeAudioRef.current = null;
    }
    setIsAdversaryPlaying(false);
  }, []);

  const stopMic = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // Ignored
      }
      recognitionRef.current = null;
    }
    setIsMicListening(false);
  }, []);

  const clearTimer = useCallback(() => {
    if (timerIntervalRef.current) {
      window.clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  }, []);

  // Cleanup on close or unmount
  useEffect(() => {
    return () => {
      stopAudio();
      stopMic();
      clearTimer();
    };
  }, [clearTimer, stopAudio, stopMic]);

  // Reset state when modal opens with new config
  useEffect(() => {
    if (!isOpen || !config) return;
    setStage("adversary_salvo");
    setTimeLeft(30.0);
    setUserText("");
    setEvaluation(null);
    setErrorMessage(null);
    stopAudio();
    stopMic();
    clearTimer();

    // Auto-vocalize adversary trap
    void playAdversaryTrap();
  }, [config, isOpen]);

  // Handle Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        handleModalClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  const handleModalClose = () => {
    stopAudio();
    stopMic();
    clearTimer();
    onClose();
  };

  const playAdversaryTrap = async () => {
    if (!config) return;
    stopAudio();
    setIsAdversaryPlaying(true);

    try {
      const res = await fetch(`${backendUrl}/api/tts/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: config.trap,
          speaker: config.speaker || "alpine",
          speed_alpha: 1.0,
        }),
      });
      if (!res.ok) throw new Error("TTS failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      activeAudioRef.current = audio;

      audio.onended = () => {
        setIsAdversaryPlaying(false);
        activeAudioRef.current = null;
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setIsAdversaryPlaying(false);
        activeAudioRef.current = null;
        URL.revokeObjectURL(url);
      };
      await audio.play();
    } catch {
      setIsAdversaryPlaying(false);
    }
  };

  const startUserRetryStage = () => {
    stopAudio();
    setStage("user_retry");
    setTimeLeft(30.0);
    setUserText("");
    setErrorMessage(null);

    // Start 30s countdown timer
    clearTimer();
    timerIntervalRef.current = window.setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 0.1) {
          clearTimer();
          // Auto-submit when time expires
          void triggerEvaluation();
          return 0;
        }
        return Math.max(0, Math.round((prev - 0.1) * 10) / 10);
      });
    }, 100);

    // Initialize speech recognition if supported
    startSpeechRecognition();
  };

  const startSpeechRecognition = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("[Rematch] Speech recognition not supported natively in this browser.");
      setErrorMessage("Browser speech recognition is unavailable here. Type your upgraded response to score this rematch.");
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        setIsMicListening(true);
      };

      recognition.onresult = (event: any) => {
        let transcript = "";
        for (let i = 0; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        if (transcript.trim()) {
          setUserText(transcript.trim());
        }
      };

      recognition.onerror = (event: any) => {
        console.warn("[Rematch] Speech recognition error:", event.error);
        setIsMicListening(false);
      };

      recognition.onend = () => {
        setIsMicListening(false);
      };

      recognition.start();
      recognitionRef.current = recognition;
    } catch (e) {
      console.warn("[Rematch] Could not start speech recognition:", e);
      setIsMicListening(false);
    }
  };

  const toggleMic = () => {
    if (isMicListening) {
      stopMic();
    } else {
      startSpeechRecognition();
    }
  };

  const triggerEvaluation = async () => {
    clearTimer();
    stopMic();

    const answer = userText.trim();
    if (!answer) {
      setErrorMessage("Please speak or enter your upgraded response to complete the rematch.");
      return;
    }

    setStage("evaluating");
    setErrorMessage(null);

    const elapsed = Math.max(2.0, 30.0 - timeLeft);
    const words = answer.split(/\s+/).filter(Boolean).length;
    const wpm = (words / elapsed) * 60;

    try {
      const res = await fetch(`${backendUrl}/api/debate/rematch/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario: config?.scenarioId || "vc_pitch",
          opponent: config?.opponent || "Adversary",
          trap: config?.trap || "",
          original_quote: config?.originalQuote || "",
          upgraded_answer: answer,
          duration_seconds: elapsed,
          original_score: config?.originalScore || 55,
          wpm: Math.round(wpm),
        }),
      });

      if (!res.ok) {
        throw new Error(`Evaluation HTTP error: ${res.status}`);
      }

      const result: RematchEvaluationResult = await res.json();
      setEvaluation(result);
      setStage("victory_summary");
    } catch (err: any) {
      console.error("[Rematch] Evaluation failed:", err);
      setErrorMessage("Evaluation failed. Please try again.");
      setStage("user_retry");
    }
  };

  const handleAcceptUpgrade = () => {
    if (config && evaluation && onUpgradeAccepted) {
      onUpgradeAccepted(config, evaluation);
    }
    handleModalClose();
  };

  if (!isOpen || !config) return null;

  // Real-time filler detection in active user text
  const detectedFillers = CANONICAL_FILLERS.filter((f) => {
    const regex = new RegExp(`\\b${f}\\b`, "i");
    return regex.test(userText);
  });

  const wordCount = userText.split(/\s+/).filter(Boolean).length;
  const elapsedSec = Math.max(1, 30.0 - timeLeft);
  const liveWpm = Math.round((wordCount / elapsedSec) * 60);

  return (
    <div
      className="modal-backdrop rematch-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Rematch This Exchange"
    >
      <section className="rematch-arena-modal">
        {/* Top Header Bar */}
        <header className="rematch-modal-header">
          <div className="rematch-header-left">
            <div className="rematch-arena-badge">
              <Flame size={14} className="text-amber-500" />
              <span>Rematch Arena</span>
            </div>
            <span className="rematch-header-title">30-Second Rapid-Fire Retry</span>
          </div>

          <div className="rematch-header-right">
            <span className="opponent-pill">
              vs <strong>{config.opponent}</strong>
            </span>
            <button
              type="button"
              className="rematch-close-btn"
              onClick={handleModalClose}
              title="Close Rematch (Esc)"
            >
              <X size={16} />
            </button>
          </div>
        </header>

        {/* Modal Main Body */}
        <div className="rematch-modal-body">
          {/* Phase 1: Adversary Salvo Stage */}
          {stage === "adversary_salvo" && (
            <div className="rematch-stage-box salvo">
              <div className="salvo-adversary-card">
                <div className="salvo-card-top">
                  <span className="salvo-badge">The Challenge Re-tested</span>
                  <button
                    type="button"
                    className={`salvo-audio-replay-btn ${isAdversaryPlaying ? "active-playing" : ""}`}
                    onClick={playAdversaryTrap}
                    title="Play adversary trap audio"
                  >
                    {isAdversaryPlaying ? (
                      <>
                        <span className="audio-equalizer-mini exec" aria-hidden="true">
                          <span className="eq-bar" />
                          <span className="eq-bar" />
                          <span className="eq-bar" />
                        </span>
                        <span>Speaking...</span>
                      </>
                    ) : (
                      <>
                        <Volume2 size={13} />
                        <span>Replay Trap Audio</span>
                      </>
                    )}
                  </button>
                </div>

                <blockquote className="salvo-trap-quote">
                  "{config.trap}"
                </blockquote>

                <div className="salvo-context-note">
                  <strong>Target Vulnerability:</strong>{" "}
                  <span>
                    {config.vulnerability || "Overcome hesitations and deliver a punchy, non-defensive answer."}
                  </span>
                </div>
              </div>

              {/* Action to enter ring */}
              <div className="salvo-footer-actions">
                <p className="salvo-instruction">
                  You have <strong>30 seconds</strong> to deliver your upgraded answer directly into the microphone.
                </p>
                <button
                  type="button"
                  className="rematch-enter-ring-btn"
                  onClick={startUserRetryStage}
                >
                  <span>Try Again (Start 30s Clock)</span>
                  <ArrowRight size={16} />
                </button>
              </div>
            </div>
          )}

          {/* Phase 2: Live 30-Second Rapid-Fire Retry */}
          {stage === "user_retry" && (
            <div className="rematch-stage-box retry">
              {/* Timer Bar & Telemetry HUD */}
              <div className="retry-hud-row">
                <div className={`countdown-clock ${timeLeft <= 7 ? "urgent" : timeLeft <= 15 ? "warning" : ""}`}>
                  <Clock size={16} />
                  <span className="clock-digits">{timeLeft.toFixed(1)}s</span>
                  <div className="countdown-progress-bar">
                    <div
                      className="countdown-progress-fill"
                      style={{ width: `${(timeLeft / 30.0) * 100}%` }}
                    />
                  </div>
                </div>

                <div className="retry-telemetry-chips">
                  <span className="telemetry-chip">
                    <strong>{wordCount}</strong> words
                  </span>
                  <span className="telemetry-chip">
                    <strong>{liveWpm}</strong> WPM
                  </span>
                  <span className={`telemetry-chip ${detectedFillers.length > 0 ? "warn" : "clean"}`}>
                    {detectedFillers.length > 0
                      ? `${detectedFillers.length} Filler${detectedFillers.length > 1 ? "s" : ""}! (${detectedFillers.join(", ")})`
                      : "Zero Fillers"}
                  </span>
                </div>
              </div>

              {/* The Trap Reminder */}
              <div className="retry-trap-reminder">
                <span className="reminder-tag">{config.opponent}:</span>
                <span className="reminder-text">"{config.trap}"</span>
              </div>

              {/* Interactive Speech Input & Transcription Box */}
              <div className="retry-speech-box">
                <div className="speech-box-header">
                  <div className="speech-status">
                    <span className={`status-dot ${isMicListening ? "pulsing-red" : "idle"}`} />
                    <span>{isMicListening ? "Microphone Live — Speak Your Answer" : "Speech Input"}</span>
                  </div>
                  <button
                    type="button"
                    className={`mic-toggle-btn ${isMicListening ? "active" : ""}`}
                    onClick={toggleMic}
                    title={isMicListening ? "Pause microphone" : "Start microphone"}
                  >
                    {isMicListening ? <Mic size={14} /> : <MicOff size={14} />}
                    <span>{isMicListening ? "Mic On" : "Mic Muted"}</span>
                  </button>
                </div>

                <textarea
                  className="retry-textarea"
                  value={userText}
                  onChange={(e) => setUserText(e.target.value)}
                  placeholder="Speak your commanding answer (or type to refine)..."
                  rows={4}
                  autoFocus
                />

                {errorMessage && (
                  <div className="rematch-error-alert">
                    <AlertTriangle size={14} />
                    <span>{errorMessage}</span>
                  </div>
                )}
              </div>

              {/* Suggested Reframe Hint (Optional Aid) */}
              {config.targetReframe && (
                <div className="retry-hint-card">
                  <div className="hint-header">
                    <Sparkles size={12} className="text-amber-500" />
                    <span>Target Concept:</span>
                  </div>
                  <p className="hint-text">"{config.targetReframe}"</p>
                </div>
              )}

              {/* Action Buttons */}
              <div className="retry-actions-row">
                <button
                  type="button"
                  className="retry-reset-btn"
                  onClick={startUserRetryStage}
                  title="Restart 30s clock"
                >
                  <RotateCcw size={14} />
                  <span>Restart 30s</span>
                </button>
                <button
                  type="button"
                  className="retry-submit-btn"
                  onClick={triggerEvaluation}
                  disabled={!userText.trim()}
                >
                  <span>Submit Upgraded Delivery</span>
                  <CheckCircle2 size={16} />
                </button>
              </div>
            </div>
          )}

          {/* Phase 3: Evaluating State */}
          {stage === "evaluating" && (
            <div className="rematch-stage-box evaluating">
              <div className="evaluating-spinner" />
              <h3>Scoring Upgraded Delivery</h3>
              <p className="eval-subtext">
                Analyzing filler reduction, speech cadence, and adversarial concession...
              </p>
            </div>
          )}

          {/* Phase 4: Victory & Scorecard Upgrade */}
          {stage === "victory_summary" && evaluation && (
            <div className="rematch-stage-box summary">
              {/* Delta Header Pill */}
              <div className="delta-victory-header">
                <div className="delta-pill-wrap">
                  <span className={`delta-score-pill ${evaluation.delta_score >= 0 ? "positive" : "negative"}`}>
                    {evaluation.delta_score >= 0 ? `▲ +${evaluation.delta_score}` : `▼ ${evaluation.delta_score}`} Points!
                  </span>
                  <span className="delta-score-range">
                    {evaluation.original_score}% → <strong>{evaluation.new_score}%</strong> Composure
                  </span>
                </div>
                <div className="delta-verdict-tag">
                  <Trophy size={14} className="text-amber-400" />
                  <span>{evaluation.verdict}</span>
                </div>
              </div>

              {/* Side-by-Side Delivery Comparison Grid */}
              <div className="comparison-columns-grid">
                {/* Previous Faltered Attempt */}
                <div className="comparison-col faltered">
                  <div className="comparison-head">
                    <span className="comparison-label red">First Attempt (Weak Moment)</span>
                    <span className="comparison-score-pill">{evaluation.original_score}%</span>
                  </div>
                  <blockquote className="comparison-quote">
                    "{config.originalQuote}"
                  </blockquote>
                  <div className="comparison-stats">
                    <span>{evaluation.fillers_before} Fillers</span>
                    <span>•</span>
                    <span>Hesitant Pacing</span>
                  </div>
                </div>

                <div className="comparison-arrow-col">
                  <ArrowRight size={18} />
                </div>

                {/* Upgraded Rematch Attempt */}
                <div className="comparison-col upgraded">
                  <div className="comparison-head">
                    <span className="comparison-label green">Rematch Delivery (Upgraded)</span>
                    <span className="comparison-score-pill green">{evaluation.new_score}%</span>
                  </div>
                  <blockquote className="comparison-quote upgraded">
                    "{userText}"
                  </blockquote>
                  <div className="comparison-stats green">
                    <span>{evaluation.fillers_after} Fillers ({evaluation.fillers_before > evaluation.fillers_after ? `-${evaluation.fillers_before - evaluation.fillers_after}` : "Clean"})</span>
                    <span>•</span>
                    <span>{evaluation.cadence_wpm.toFixed(0)} WPM ({evaluation.pacing_verdict})</span>
                  </div>
                </div>
              </div>

              {/* Adversary Concession Reaction Box */}
              <div className="adversary-reaction-box">
                <div className="reaction-header">
                  <Zap size={13} className="text-emerald-500" />
                  <strong>Adversary Concession:</strong>
                </div>
                <p className="reaction-text">{evaluation.adversary_reaction}</p>
                <p className="tactical-note">{evaluation.tactical_analysis}</p>
              </div>

              {/* Victory Footer Actions */}
              <div className="summary-actions-row">
                <button
                  type="button"
                  className="retry-again-btn"
                  onClick={startUserRetryStage}
                >
                  <RotateCcw size={14} />
                  <span>Try Another 30s Retry</span>
                </button>
                <button
                  type="button"
                  className="accept-upgrade-btn"
                  onClick={handleAcceptUpgrade}
                >
                  <CheckCircle2 size={16} />
                  <span>Accept & Apply to Debrief</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};
