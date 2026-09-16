import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  Award,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CornerDownRight,
  Lightbulb,
  ShieldAlert,
  Sparkles,
  Trophy,
  X,
} from "lucide-react";
import type { DebateReportEvent, TelemetryEvent } from "../types";
import { MomentReplay } from "./MomentReplay";

interface DebriefModalProps {
  report: DebateReportEvent;
  telemetry: TelemetryEvent;
  transcriptCount: number;
  interruptions: number;
  onClose: () => void;
}

export const DebriefModal: React.FC<DebriefModalProps> = ({
  report,
  telemetry,
  transcriptCount,
  interruptions,
  onClose,
}) => {
  const [showChapters, setShowChapters] = useState(false);
  const m = report.metrics || {};

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

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
    { label: "Overall Score", value: `${Math.round(report.overall_score)}/100`, highlight: true },
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
          <div className="debrief-score-pill">
            <span className="score-pill-label">Performance</span>
            <span className="score-pill-value">{Math.round(report.overall_score)}%</span>
          </div>
          <button
            type="button"
            className="debrief-complete-btn"
            onClick={onClose}
          >
            <CheckCircle2 size={16} />
            <span>Complete Session</span>
          </button>
          <button
            type="button"
            className="debrief-close-round-btn"
            onClick={onClose}
            title="Close Debrief (Esc)"
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

                  <div className="reframes-stack">
                    {report.executive_reframes.map((rf, idx) => (
                      <div key={idx} className="reframe-item">
                        <div className="reframe-exchange">
                          <div className="reframe-bubble spoken">
                            <span className="bubble-tag original">Your Verbatim Spoken Words</span>
                            <blockquote className="bubble-quote">"{rf.original_quote}"</blockquote>
                          </div>

                          <div className="reframe-arrow-divider">
                            <CornerDownRight size={16} />
                          </div>

                          <div className="reframe-bubble winning">
                            <span className="bubble-tag executive">Executive Reframe</span>
                            <blockquote className="bubble-quote winning-text">"{rf.executive_reframe}"</blockquote>
                          </div>
                        </div>

                        {rf.rationale && (
                          <div className="reframe-rationale-box">
                            <strong>Tactical Rationale:</strong>
                            <span>{rf.rationale}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Weakest vs Strongest Answers Split Grid */}
              {(report.weakest_answer || report.strongest_answer) && (
                <section className="debrief-answers-split" aria-label="Weakest and Strongest Answers">
                  {report.weakest_answer && (
                    <div className="answer-card-pro faltered">
                      <div className="answer-badge text-red-600">
                        <AlertCircle size={15} />
                        <span>Weakest Moment</span>
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
                    </div>
                  )}

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
              <MomentReplay bookmarks={report.bookmarks} />
            </section>
          )}

          {/* Bottom Action Bar */}
          <footer className="debrief-footer-actions">
            <button
              type="button"
              className="debrief-primary-finish-btn"
              onClick={onClose}
            >
              <CheckCircle2 size={18} />
              <span>Conclude Sparring & Return to Overview</span>
            </button>
          </footer>
        </div>
      </main>
    </div>
  );
};
