import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Award,
  Calculator,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CornerDownRight,
  Download,
  FileCheck,
  Flame,
  Hash,
  Headphones,
  Lightbulb,
  RotateCcw,
  Share2,
  ShieldAlert,
  Sparkles,
  Trophy,
  Volume2,
  X,
} from "lucide-react";
import type { DebateReportEvent, RematchConfig, RematchEvaluationResult, TelemetryEvent } from "../types";
import type { RecordedTurnAudio } from "../audio";
import { MomentReplay } from "./MomentReplay";
import { RematchModal } from "./RematchModal";

interface DebriefModalProps {
  report: DebateReportEvent;
  telemetry: TelemetryEvent;
  transcriptCount: number;
  interruptions: number;
  onClose: () => void;
  recordedUserTurns?: RecordedTurnAudio[];
  speaker?: string;
  backendUrl?: string;
}

function findMatchingTurnAudio(
  quote: string,
  turns: RecordedTurnAudio[] = []
): RecordedTurnAudio | null {
  if (!turns || turns.length === 0) return null;
  const cleanQ = quote.toLowerCase().replace(/[^\w\s]/g, "").trim();
  if (!cleanQ) return turns[0] ?? null;

  // 1. Direct substring inclusion or exact match
  for (const t of turns) {
    const cleanT = t.transcript.toLowerCase().replace(/[^\w\s]/g, "").trim();
    if (cleanT.includes(cleanQ) || cleanQ.includes(cleanT)) {
      return t;
    }
  }

  // 2. Token overlap heuristic
  const qWords = new Set(cleanQ.split(/\s+/).filter((w) => w.length > 2));
  if (qWords.size > 0) {
    let bestTurn: RecordedTurnAudio | null = null;
    let bestScore = 0;
    for (const t of turns) {
      const cleanT = t.transcript.toLowerCase().replace(/[^\w\s]/g, "").trim();
      const tWords = cleanT.split(/\s+/);
      let matchCount = 0;
      for (const w of tWords) {
        if (qWords.has(w)) matchCount++;
      }
      const score = matchCount / qWords.size;
      if (score > bestScore && score >= 0.25) {
        bestScore = score;
        bestTurn = t;
      }
    }
    if (bestTurn) return bestTurn;
  }

  // 3. Fallback: return first recorded turn
  return turns[0] ?? null;
}

export const DebriefModal: React.FC<DebriefModalProps> = ({
  report,
  telemetry,
  transcriptCount,
  interruptions,
  onClose,
  recordedUserTurns = [],
  speaker = "alpine",
  backendUrl = "http://localhost:8000",
}) => {
  const [showChapters, setShowChapters] = useState(false);
  const [playingTrack, setPlayingTrack] = useState<{ id: string; type: "user" | "executive" } | null>(null);
  const [loadingTrackId, setLoadingTrackId] = useState<string | null>(null);

  // Rematch State
  const [rematchConfig, setRematchConfig] = useState<RematchConfig | null>(null);
  const [upgradedMoments, setUpgradedMoments] = useState<Set<string>>(new Set());
  const [rematchDeltas, setRematchDeltas] = useState<Map<string, RematchEvaluationResult>>(new Map());
  const [overallScore, setOverallScore] = useState<number>(Math.round(report.overall_score));

  // Share & PDF Export State
  const [shareCopied, setShareCopied] = useState(false);
  const [sharing, setSharing] = useState(false);

  const handleShareDebrief = async () => {
    try {
      setSharing(true);
      const res = await fetch(`${backendUrl}/api/debrief/share`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report }),
      });
      if (!res.ok) throw new Error("Failed to create share link");
      const data = await res.json();
      const shareUrl = `${window.location.origin}${data.share_url}`;
      await navigator.clipboard.writeText(shareUrl);
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 3500);
    } catch (err) {
      console.error("Error sharing debrief:", err);
    } finally {
      setSharing(false);
    }
  };

  const handleExportPdf = () => {
    const sessionId = report.session_id || report.share_id || "session";
    const pdfUrl = `${backendUrl}/api/debrief/${sessionId}/pdf`;
    window.open(pdfUrl, "_blank");
  };

  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const execAudioCacheRef = useRef<Map<string, string>>(new Map());

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
    setPlayingTrack(null);
  }, []);

  const handleClose = useCallback(() => {
    stopAudio();
    onClose();
  }, [onClose, stopAudio]);

  const handleStartWeakestRematch = useCallback(() => {
    if (!report.weakest_answer) return;
    stopAudio();
    const trap =
      report.weakest_answer.vulnerability
        ? `Stop right there. You claimed: "${report.weakest_answer.quote}", but ${report.weakest_answer.vulnerability}. How do you defend that?`
        : `Stop right there. Wrap it up and give me the bottom line.`;

    setRematchConfig({
      id: "weakest_moment",
      scenarioId: report.scenario || "vc_pitch",
      title: "Weakest Moment Retry",
      opponent: "Adversary",
      speaker: speaker || "alpine",
      trap,
      originalQuote: report.weakest_answer.quote,
      originalScore: 52,
      targetReframe: report.weakest_answer.why_faltered,
      vulnerability: report.weakest_answer.vulnerability,
      sourceType: "weakest_answer",
    });
  }, [report.weakest_answer, speaker, stopAudio]);

  const handleStartBookmarkRematch = useCallback((bookmark: any) => {
    stopAudio();
    const trap = bookmark.why || `Stop right there. Back up your claim with data.`;
    setRematchConfig({
      id: bookmark.id || `bookmark-${bookmark.round}-${bookmark.timestamp}`,
      scenarioId: report.scenario || "vc_pitch",
      title: `Round ${bookmark.round} Key Moment`,
      opponent: "Adversary",
      speaker: speaker || "alpine",
      trap: `Hold on. ${trap}`,
      originalQuote: bookmark.quote || "Our position holds up.",
      originalScore: 55,
      targetReframe: bookmark.reframe,
      vulnerability: bookmark.label,
      sourceType: "moment_replay",
    });
  }, [speaker, stopAudio]);

  const handleStartReframeRematch = useCallback((rf: any, idx: number) => {
    stopAudio();
    setRematchConfig({
      id: `reframe-${idx}`,
      scenarioId: report.scenario || "vc_pitch",
      title: `Tactical Upgrade #${idx + 1}`,
      opponent: "Adversary",
      speaker: speaker || "alpine",
      trap: `Hold on. Enough hand-waving on: "${rf.original_quote}". Give me the exact number or take it back.`,
      originalQuote: rf.original_quote,
      originalScore: 58,
      targetReframe: rf.executive_reframe,
      vulnerability: rf.rationale,
      sourceType: "reframe",
    });
  }, [speaker, stopAudio]);

  const handleUpgradeAccepted = useCallback((cfg: RematchConfig, result: RematchEvaluationResult) => {
    setUpgradedMoments((prev) => new Set([...prev, cfg.id]));
    setRematchDeltas((prev) => new Map(prev).set(cfg.id, result));
    if (result.delta_score > 0) {
      setOverallScore((prev) => Math.min(100, Math.round(prev + Math.max(2, result.delta_score * 0.2))));
    }
  }, []);

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleClose]);

  // Cleanup active audio and cached object URLs on unmount
  useEffect(() => {
    return () => {
      stopAudio();
      for (const url of execAudioCacheRef.current.values()) {
        try {
          URL.revokeObjectURL(url);
        } catch {
          // Ignored
        }
      }
      execAudioCacheRef.current.clear();
    };
  }, [stopAudio]);

  const handleToggleUserAudio = useCallback(
    (trackId: string, turnAudio: RecordedTurnAudio | null) => {
      if (!turnAudio || !turnAudio.audioUrl) return;

      if (playingTrack?.id === trackId && playingTrack.type === "user") {
        stopAudio();
        return;
      }

      stopAudio();

      const audio = new Audio(turnAudio.audioUrl);
      activeAudioRef.current = audio;
      setPlayingTrack({ id: trackId, type: "user" });

      audio.onended = () => {
        setPlayingTrack((curr) => (curr?.id === trackId && curr.type === "user" ? null : curr));
        activeAudioRef.current = null;
      };
      audio.onerror = () => {
        setPlayingTrack((curr) => (curr?.id === trackId && curr.type === "user" ? null : curr));
        activeAudioRef.current = null;
      };
      audio.play().catch((err) => {
        console.warn("[Debrief Audio] User audio playback failed:", err);
        setPlayingTrack(null);
        activeAudioRef.current = null;
      });
    },
    [playingTrack, stopAudio]
  );

  const handleToggleExecAudio = useCallback(
    async (trackId: string, textToSpeak: string) => {
      if (playingTrack?.id === trackId && playingTrack.type === "executive") {
        stopAudio();
        return;
      }

      stopAudio();

      let audioUrl = execAudioCacheRef.current.get(textToSpeak);
      if (!audioUrl) {
        setLoadingTrackId(trackId);
        try {
          const apiBase = backendUrl || "http://localhost:8000";
          const res = await fetch(`${apiBase}/api/tts/synthesize`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text: textToSpeak,
              speaker: speaker || "alpine",
              speed_alpha: 1.0,
            }),
          });
          if (!res.ok) {
            throw new Error(`Synthesis HTTP error: ${res.status}`);
          }
          const blob = await res.blob();
          audioUrl = URL.createObjectURL(blob);
          execAudioCacheRef.current.set(textToSpeak, audioUrl);
        } catch (err) {
          console.error("[Debrief Audio] Executive synthesis failed:", err);
          setLoadingTrackId(null);
          return;
        } finally {
          setLoadingTrackId(null);
        }
      }

      const audio = new Audio(audioUrl);
      activeAudioRef.current = audio;
      setPlayingTrack({ id: trackId, type: "executive" });

      audio.onended = () => {
        setPlayingTrack((curr) => (curr?.id === trackId && curr.type === "executive" ? null : curr));
        activeAudioRef.current = null;
      };
      audio.onerror = () => {
        setPlayingTrack((curr) => (curr?.id === trackId && curr.type === "executive" ? null : curr));
        activeAudioRef.current = null;
      };
      audio.play().catch((err) => {
        console.warn("[Debrief Audio] Executive audio playback failed:", err);
        setPlayingTrack(null);
        activeAudioRef.current = null;
      });
    },
    [backendUrl, playingTrack, speaker, stopAudio]
  );

  const speakerLabel = speaker ? speaker.charAt(0).toUpperCase() + speaker.slice(1) : "Executive";
  const m = report.metrics || {};

  const composureVal =
    m.composure_score !== undefined
      ? Math.round(Number(m.composure_score))
      : Math.round(telemetry.composure_score);
  const cadenceVal =
    m.current_wpm !== undefined
      ? Math.round(Number(m.current_wpm))
      : Math.round(telemetry.current_wpm);
  const fillersVal =
    m.filler_word_count !== undefined ? Number(m.filler_word_count) : telemetry.filler_word_count;
  const pressureVal =
    m.pressure_level !== undefined ? `${m.pressure_level}/5` : `${telemetry.pressure_level}/5`;
  const turnsVal = m.turns_count !== undefined ? Number(m.turns_count) : transcriptCount;
  const bargeInsVal = m.barge_ins !== undefined ? Number(m.barge_ins) : interruptions;

  const scoreMetrics = [
    { label: "Overall Score", value: `${overallScore}/100`, highlight: true },
    { label: "Composure Index", value: `${composureVal}/100` },
    { label: "Cadence", value: `${cadenceVal} WPM` },
    { label: "Fillers Detected", value: fillersVal.toString() },
    { label: "Peak Pressure", value: pressureVal },
    { label: "Sparring Rounds", value: turnsVal.toString() },
    { label: "Barge-ins Seized", value: bargeInsVal.toString() },
  ];

  const detectedFillers = Array.isArray(m.detected_fillers)
    ? (m.detected_fillers as string[])
    : [];

  return (
    <div
      className="debrief-fullscreen-wrapper"
      role="dialog"
      aria-modal="true"
      aria-label="Executive Sparring Debrief"
    >
      {/* Sticky Executive Top Bar */}
      <header className="debrief-fullscreen-topbar">
        <div className="debrief-topbar-left">
          <div className="debrief-brand-pill">
            <Trophy size={14} className="debrief-trophy-icon" />
            <span>Miles Executive Debrief</span>
          </div>
          <div className="debrief-topbar-title">
            <h2>{report.verdict}</h2>
            {report.verdict_description && (
              <p className="debrief-topbar-desc">{report.verdict_description}</p>
            )}
          </div>
        </div>

        <div className="debrief-topbar-right">
          <button
            type="button"
            className={`debrief-action-btn ${shareCopied ? "copied" : ""}`}
            onClick={handleShareDebrief}
            disabled={sharing}
            title="Generate shareable read-only link for pitch coaches or mentors"
          >
            <Share2 size={14} />
            <span>{sharing ? "Sharing..." : shareCopied ? "Link Copied!" : "Share Debrief"}</span>
          </button>
          <button
            type="button"
            className="debrief-action-btn"
            onClick={handleExportPdf}
            title="Download executive 1-page PDF summary"
          >
            <Download size={14} />
            <span>Export PDF</span>
          </button>
          <div className="debrief-score-pill">
            <span className="score-pill-label">Performance</span>
            <span className="score-pill-value">{overallScore}%</span>
          </div>
          <button
            type="button"
            className="debrief-complete-btn"
            onClick={handleClose}
          >
            <CheckCircle2 size={16} />
            <span>Complete Session</span>
          </button>
          <button
            type="button"
            className="debrief-close-round-btn"
            onClick={handleClose}
            title="Close Debrief (Esc)"
            aria-label="Close debrief"
          >
            <X size={18} />
          </button>
        </div>
      </header>

      {/* Main Full-Screen Viewport Content */}
      <main className="debrief-fullscreen-content">
        <div className="debrief-content-container">
          {/* Executive Metrics Strip */}
          <section className="debrief-metrics-strip" aria-label="Executive Performance Metrics">
            {scoreMetrics.map((item) => (
              <div
                key={item.label}
                className={`debrief-metric-card ${item.highlight ? "metric-highlight" : ""}`}
              >
                <span className="metric-label">{item.label}</span>
                <strong className="metric-val">{item.value}</strong>
              </div>
            ))}
          </section>

          {/* Two-Column Executive Analysis Grid */}
          <div className="debrief-columns-grid">
            {/* Left Primary Column: Tactical Reframes & Core Exchanges */}
            <div className="debrief-col-main">
              {/* Forensic Math & Contradiction Trap Detector Audit Card */}
              {report.math_audit && report.math_audit.discrepancies && report.math_audit.discrepancies.length > 0 && (
                <section className="debrief-section-card math-audit-card" aria-label="Forensic Math & Contradiction Audit">
                  <div className="section-card-header">
                    <div className="section-title-wrap">
                      <Calculator size={16} className="text-amber-400" />
                      <h3>Forensic Math & Contradiction Trap Detector</h3>
                    </div>
                    <span className="section-count-badge audit-badge-warn">
                      {report.math_audit.discrepancies.length} Arithmetic Trap{report.math_audit.discrepancies.length > 1 ? "s" : ""} Caught
                    </span>
                  </div>
                  <p className="math-audit-description">
                    Our asynchronous claim validator monitored your quantitative figures across all debate rounds against relational unit economics (ARR vs Customers × ACV, Runway vs Cash / Monthly Burn, and Intra-Session Number Shifts).
                  </p>
                  <div className="audit-items-list">
                    {report.math_audit.discrepancies.map((m, idx) => (
                      <div key={idx} className="audit-item math-discrepancy">
                        <div className="audit-item-top">
                          <span className="audit-metric-name">{m.rule_type.replace(/_/g, " ").toUpperCase()}</span>
                          <span className="audit-comparison">
                            Discrepancy Gap: <strong className="text-rose-400">{typeof m.discrepancy_gap === "number" ? m.discrepancy_gap.toLocaleString() : m.discrepancy_gap}</strong>
                          </span>
                        </div>
                        <p className="audit-item-note">{m.description}</p>
                        {m.lethal_salvo && (
                          <div className="audit-rectification-salvo">
                            <strong>Adversary Lethal Trap:</strong> "{m.lethal_salvo}"
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Ground-Truth & Numeric Cross-Examination Audit */}
              {report.ground_truth_audit && (report.ground_truth_audit.has_context || report.ground_truth_audit.total_audited_metrics > 0) && (
                <section className="debrief-section-card ground-truth-audit-card" aria-label="Ground Truth & Numeric Audit">
                  <div className="section-card-header">
                    <div className="section-title-wrap">
                      <FileCheck size={16} className="text-emerald-500" />
                      <h3>Ground-Truth & Numeric Audit</h3>
                    </div>
                    <span className={`section-count-badge ${report.ground_truth_audit.discrepancy_count > 0 ? "audit-badge-warn" : "audit-badge-good"}`}>
                      {report.ground_truth_audit.factual_accuracy_score}% Factual Accuracy ({report.ground_truth_audit.verified_count} Verified / {report.ground_truth_audit.discrepancy_count} Blunder{report.ground_truth_audit.discrepancy_count !== 1 ? "s" : ""})
                    </span>
                  </div>

                  <div className="audit-document-meta">
                    <span className="doc-pill">{report.ground_truth_audit.document_type.replace("_", " ").toUpperCase()}</span>
                    <strong className="doc-title">{report.ground_truth_audit.document_title}</strong>
                  </div>

                  {/* Discrepancies / Contradictions */}
                  {report.ground_truth_audit.discrepancies.length > 0 && (
                    <div className="audit-issues-block">
                      <div className="audit-subtitle text-rose-400">
                        <AlertTriangle size={14} />
                        <span>Contradictions & Misstated Metrics ({report.ground_truth_audit.discrepancies.length})</span>
                      </div>
                      <div className="audit-items-list">
                        {report.ground_truth_audit.discrepancies.map((d, idx) => (
                          <div key={idx} className="audit-item discrepancy">
                            <div className="audit-item-top">
                              <span className="audit-metric-name">{d.metric_name}</span>
                              <span className="audit-comparison">
                                Claimed: <strong className="text-rose-400">"{d.user_stated_raw}"</strong> vs Document: <strong className="text-emerald-400">"{d.ground_truth_raw}"</strong>
                              </span>
                            </div>
                            <p className="audit-item-note">{d.discrepancy_note}</p>
                            {d.rectification_salvo && (
                              <div className="audit-rectification-salvo">
                                <strong>Adversary Rectification:</strong> "{d.rectification_salvo}"
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Verified Metrics */}
                  {report.ground_truth_audit.verified_metrics.length > 0 && (
                    <div className="audit-verified-block">
                      <div className="audit-subtitle text-emerald-400">
                        <CheckCircle2 size={14} />
                        <span>Accurately Defended Metrics ({report.ground_truth_audit.verified_metrics.length})</span>
                      </div>
                      <div className="audit-items-list">
                        {report.ground_truth_audit.verified_metrics.map((v, idx) => (
                          <div key={idx} className="audit-item verified">
                            <div className="audit-item-top">
                              <span className="audit-metric-name">{v.metric_name}</span>
                              <span className="audit-verified-badge">
                                Cited: "{v.user_stated_raw}" (Matches {v.ground_truth_raw})
                              </span>
                            </div>
                            <p className="audit-item-note">{v.discrepancy_note}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </section>
              )}

              {/* Executive Reframes ("What You Should Have Said") */}
              {report.executive_reframes && report.executive_reframes.length > 0 && (
                <section className="debrief-section-card" aria-label="Executive Reframes">
                  <div className="section-card-header">
                    <div className="section-title-wrap">
                      <Sparkles size={16} className="text-amber-500" />
                      <h3>What You Should Have Said</h3>
                    </div>
                    <span className="section-count-badge">
                      {report.executive_reframes.length} Tactical Upgrade{report.executive_reframes.length > 1 ? "s" : ""}
                    </span>
                  </div>

                  {/* Audio Contrast Explainer Banner */}
                  <div className="tape-contrast-banner">
                    <Headphones size={16} className="tape-banner-icon" />
                    <div className="tape-banner-content">
                      <strong>Audio Contrast: Listen to the Tape</strong>
                      <p>
                        Audibly compare your actual microphone delivery against the adversary's commanding executive delivery. Click below to hear the visceral difference in pacing, filler usage, and inflection.
                      </p>
                    </div>
                  </div>

                  <div className="reframes-stack">
                    {report.executive_reframes.map((rf, idx) => {
                      const trackId = `reframe-${idx}`;
                      const matchingTurn = findMatchingTurnAudio(rf.original_quote, recordedUserTurns);
                      const isUserPlaying = playingTrack?.id === trackId && playingTrack.type === "user";
                      const isExecPlaying = playingTrack?.id === trackId && playingTrack.type === "executive";
                      const isExecLoading = loadingTrackId === trackId;

                      return (
                        <div key={idx} className="reframe-item">
                          <div className="reframe-exchange">
                            <div className="reframe-bubble spoken">
                              <div className="bubble-header-row">
                                <span className="bubble-tag original">Your Verbatim Spoken Words</span>
                                {matchingTurn && (
                                  <span className="turn-timestamp-pill">
                                    Round {matchingTurn.turnIndex} • {matchingTurn.durationSec.toFixed(1)}s
                                  </span>
                                )}
                              </div>
                              <blockquote className="bubble-quote">"{rf.original_quote}"</blockquote>
                              <div className="bubble-tape-dock">
                                <button
                                  type="button"
                                  className={`tape-listen-btn spoken-audio-btn ${isUserPlaying ? "active-playing" : ""}`}
                                  onClick={() => handleToggleUserAudio(trackId, matchingTurn)}
                                  disabled={!matchingTurn}
                                  title={matchingTurn ? "Hear your exact mic audio during this turn" : "Microphone audio not captured for this round"}
                                >
                                  {isUserPlaying ? (
                                    <>
                                      <span className="audio-equalizer-mini" aria-hidden="true">
                                        <span className="eq-bar" />
                                        <span className="eq-bar" />
                                        <span className="eq-bar" />
                                      </span>
                                      <span>Pause Your Tape</span>
                                    </>
                                  ) : (
                                    <>
                                      <Volume2 size={13} />
                                      <span>{matchingTurn ? "Listen to Your Tape" : "Audio Not Captured"}</span>
                                    </>
                                  )}
                                </button>
                              </div>
                            </div>

                            <div className="reframe-arrow-divider">
                              <CornerDownRight size={16} />
                            </div>

                            <div className="reframe-bubble winning">
                              <div className="bubble-header-row">
                                <span className="bubble-tag executive">Executive Reframe</span>
                                <span className="turn-timestamp-pill adversary">
                                  Neural Voice • {speakerLabel}
                                </span>
                              </div>
                              <blockquote className="bubble-quote winning-text">"{rf.executive_reframe}"</blockquote>
                              <div className="bubble-tape-dock">
                                <button
                                  type="button"
                                  className={`tape-listen-btn exec-audio-btn ${isExecPlaying ? "active-playing" : ""} ${isExecLoading ? "loading" : ""}`}
                                  onClick={() => handleToggleExecAudio(trackId, rf.executive_reframe)}
                                  disabled={isExecLoading}
                                  title={`Listen to the winning reframe vocalized in ${speakerLabel}'s voice`}
                                >
                                  {isExecLoading ? (
                                    <>
                                      <span className="audio-mini-spinner" aria-hidden="true" />
                                      <span>Vocalizing Delivery...</span>
                                    </>
                                  ) : isExecPlaying ? (
                                    <>
                                      <span className="audio-equalizer-mini exec" aria-hidden="true">
                                        <span className="eq-bar" />
                                        <span className="eq-bar" />
                                        <span className="eq-bar" />
                                      </span>
                                      <span>Pause Executive Delivery</span>
                                    </>
                                  ) : (
                                    <>
                                      <Sparkles size={13} />
                                      <span>Listen to Executive Delivery</span>
                                    </>
                                  )}
                                </button>
                                <button
                                  type="button"
                                  className="rematch-reframe-btn"
                                  onClick={() => handleStartReframeRematch(rf, idx)}
                                  title="Step into the ring for a 30-second rapid retry of this reframe"
                                >
                                  <Flame size={12} className="text-amber-500" />
                                  <span>Re-spar</span>
                                </button>
                              </div>
                            </div>
                          </div>

                          {rf.rationale && (
                            <div className="reframe-rationale-box">
                              <strong>Tactical Rationale:</strong>
                              <span>{rf.rationale}</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* Weakest vs Strongest Answers Split Grid */}
              {(report.weakest_answer || report.strongest_answer) && (
                <section className="debrief-answers-split" aria-label="Weakest and Strongest Answers">
                  {report.weakest_answer && (() => {
                    const matchingWeakestTurn = findMatchingTurnAudio(report.weakest_answer.quote, recordedUserTurns);
                    const isWeakestPlaying = playingTrack?.id === "weakest-moment" && playingTrack.type === "user";
                    const isWeakestOvercome = upgradedMoments.has("weakest_moment");
                    const weakestDelta = rematchDeltas.get("weakest_moment");

                    return (
                      <div className="answer-card-pro faltered">
                        <div className="answer-card-header-row">
                          <div className="answer-badge text-red-600">
                            <AlertCircle size={15} />
                            <span>Weakest Moment</span>
                          </div>
                          {isWeakestOvercome && weakestDelta && (
                            <span className="rematch-conquered-pill">
                              <CheckCircle2 size={13} className="text-emerald-500" />
                              <span>Rematch Won (+{weakestDelta.delta_score}pts)</span>
                            </span>
                          )}
                        </div>
                        <blockquote className="answer-quote-pro">"{report.weakest_answer.quote}"</blockquote>
                        <div className="answer-critique">
                          <p className="critique-item">
                            <strong>Why faltered:</strong> {report.weakest_answer.why_faltered}
                          </p>
                          {report.weakest_answer.vulnerability && (
                            <p className="critique-item">
                              <strong>Vulnerability exposed:</strong> {report.weakest_answer.vulnerability}
                            </p>
                          )}
                        </div>
                        <div className="weakest-actions-dock">
                          {matchingWeakestTurn && (
                            <button
                              type="button"
                              className={`tape-listen-btn spoken-audio-btn ${isWeakestPlaying ? "active-playing" : ""}`}
                              onClick={() => handleToggleUserAudio("weakest-moment", matchingWeakestTurn)}
                              title="Play your exact microphone audio during this faltered moment"
                            >
                              {isWeakestPlaying ? (
                                <>
                                  <span className="audio-equalizer-mini" aria-hidden="true">
                                    <span className="eq-bar" />
                                    <span className="eq-bar" />
                                    <span className="eq-bar" />
                                  </span>
                                  <span>Pause Replay</span>
                                </>
                              ) : (
                                <>
                                  <Volume2 size={13} />
                                  <span>Listen to Hesitation ({matchingWeakestTurn.durationSec.toFixed(1)}s)</span>
                                </>
                              )}
                            </button>
                          )}

                          <button
                            type="button"
                            className="rematch-action-btn weakest"
                            onClick={handleStartWeakestRematch}
                            title="Drop back into the ring for an immediate 30-second rapid retry against this exact trap"
                          >
                            <Flame size={14} className="text-amber-500" />
                            <span>{isWeakestOvercome ? "Re-spar Again" : "Re-spar This Exchange (30s Retry)"}</span>
                          </button>
                        </div>
                      </div>
                    );
                  })()}

                  {report.strongest_answer && (
                    <div className="answer-card-pro commanding">
                      <div className="answer-badge text-emerald-600">
                        <Award size={15} />
                        <span>Strongest Answer</span>
                      </div>
                      <blockquote className="answer-quote-pro">"{report.strongest_answer.quote}"</blockquote>
                      <div className="answer-critique">
                        <p className="critique-item">
                          <strong>Why commanding:</strong> {report.strongest_answer.why_commanding}
                        </p>
                        {report.strongest_answer.evidence_cited && (
                          <p className="critique-item">
                            <strong>Evidence cited:</strong> {report.strongest_answer.evidence_cited}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </section>
              )}
            </div>

            {/* Right Strategic Sidebar: Vulnerabilities, Coaching & Chapters */}
            <aside className="debrief-col-side">
              {/* Vulnerabilities Exposed */}
              {report.key_weaknesses && report.key_weaknesses.length > 0 && (
                <div className="debrief-sidebar-card">
                  <div className="sidebar-card-header">
                    <ShieldAlert size={16} className="text-red-500" />
                    <h4>Vulnerabilities Exposed</h4>
                  </div>
                  <ul className="sidebar-list">
                    {report.key_weaknesses.map((item, idx) => (
                      <li key={idx} className="sidebar-list-item vulnerability">
                        <span className="bullet red" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Coaching Recommendations */}
              {report.coaching_tips && report.coaching_tips.length > 0 && (
                <div className="debrief-sidebar-card">
                  <div className="sidebar-card-header">
                    <Lightbulb size={16} className="text-amber-500" />
                    <h4>Adversary Coaching</h4>
                  </div>
                  <ul className="sidebar-list">
                    {report.coaching_tips.map((item, idx) => (
                      <li key={idx} className="sidebar-list-item recommendation">
                        <span className="bullet amber" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Detected Fillers / Disfluency Chips */}
              {detectedFillers.length > 0 && (
                <div className="debrief-sidebar-card">
                  <div className="sidebar-card-header">
                    <h4>Detected Fillers & Crutches</h4>
                  </div>
                  <div className="fillers-chips-wrap">
                    {detectedFillers.map((word, idx) => (
                      <span key={`${word}-${idx}`} className="filler-pill">
                        "{word}"
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Debate Chapters Accordion */}
              {report.chapters && report.chapters.length > 0 && (
                <div className="debrief-sidebar-card chapters">
                  <button
                    type="button"
                    className="chapters-accordion-btn"
                    onClick={() => setShowChapters((prev) => !prev)}
                  >
                    <div className="chapters-btn-left">
                      <h4>Sparring Chapters</h4>
                      <span className="chapters-count-pill">{report.chapters.length} Rounds</span>
                    </div>
                    {showChapters ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>

                  {showChapters && (
                    <div className="chapters-content-list">
                      {report.chapters.map((ch) => (
                        <div key={ch.round} className="chapter-entry">
                          <div className="chapter-entry-head">
                            <span className="chapter-round-tag">Round {ch.round}</span>
                            <span className="chapter-score-pill">{ch.score}/100</span>
                          </div>
                          <strong className="chapter-entry-title">{ch.title}</strong>
                          <p className="chapter-entry-summary">{ch.summary}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </aside>
          </div>

          {/* Full-Width Interactive Moment Replay Shelf */}
          {report.bookmarks && report.bookmarks.length > 0 && (
            <section className="debrief-replay-section" aria-label="Interactive Moment Replay Timeline">
              <MomentReplay bookmarks={report.bookmarks} onRematch={handleStartBookmarkRematch} />
            </section>
          )}

          {/* Bottom Action Bar */}
          <footer className="debrief-footer-actions">
            <button
              type="button"
              className="debrief-primary-finish-btn"
              onClick={handleClose}
            >
              <CheckCircle2 size={18} />
              <span>Conclude Sparring & Return to Overview</span>
            </button>
          </footer>
        </div>
      </main>

      <RematchModal
        isOpen={!!rematchConfig}
        config={rematchConfig}
        backendUrl={backendUrl}
        onClose={() => setRematchConfig(null)}
        onUpgradeAccepted={handleUpgradeAccepted}
      />
    </div>
  );
};
