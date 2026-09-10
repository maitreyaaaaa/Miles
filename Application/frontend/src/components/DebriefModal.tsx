import React, { useState } from "react";
import { AlertCircle, Award, CheckCircle2, ChevronDown, ChevronUp, Sparkles, Trophy, X } from "lucide-react";
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
    { label: "Overall Score", value: Math.round(report.overall_score).toString(), highlight: true },
    { label: "Composure", value: composureVal.toString() },
    { label: "Cadence", value: `${cadenceVal} WPM` },
    { label: "Fillers", value: fillersVal.toString() },
    { label: "Pressure", value: pressureVal },
    { label: "Turns", value: turnsVal.toString() },
    { label: "Barge-ins", value: bargeInsVal.toString() },
  ];

  const detectedFillers = Array.isArray(m.detected_fillers)
    ? (m.detected_fillers as string[])
    : [];

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="debrief debrief-2"
        role="dialog"
        aria-modal="true"
        aria-label="Debrief 2.0 report"
      >
        {/* Header */}
        <header className="debrief-header-pro">
          <div>
            <div className="debrief-eyebrow">
              <Trophy size={14} className="text-amber-400" />
              <span>Debrief 2.0 • Post-Sparring Analysis</span>
            </div>
            <h2>{report.verdict}</h2>
            {report.verdict_description && (
              <p className="debrief-verdict-desc">{report.verdict_description}</p>
            )}
          </div>
          <button
            type="button"
            className="ghost-icon debrief-close-btn"
            onClick={onClose}
            title="Close Debrief"
          >
            <X size={20} />
          </button>
        </header>

        {/* Scorecard Metrics Bar */}
        <div className="final-metrics">
          {scoreMetrics.map((item) => (
            <div key={item.label} className={item.highlight ? "metric-highlight" : ""}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>

        {/* Interactive Moment Replay Timeline */}
        {report.bookmarks && report.bookmarks.length > 0 && (
          <MomentReplay bookmarks={report.bookmarks} />
        )}

        {/* Weakest vs Strongest Answers Split Cards */}
        {(report.weakest_answer || report.strongest_answer) && (
          <div className="answers-split-grid">
            {report.weakest_answer && (
              <div className="answer-card faltered">
                <div className="answer-header text-red-400">
                  <AlertCircle size={15} />
                  <span>Weakest Answer</span>
                </div>
                <blockquote className="answer-quote">"{report.weakest_answer.quote}"</blockquote>
                <p className="answer-why">
                  <strong>Why faltered:</strong> {report.weakest_answer.why_faltered}
                </p>
                {report.weakest_answer.vulnerability && (
                  <p className="answer-sub">
                    <strong>Vulnerability exposed:</strong> {report.weakest_answer.vulnerability}
                  </p>
                )}
              </div>
            )}

            {report.strongest_answer && (
              <div className="answer-card commanding">
                <div className="answer-header text-emerald-400">
                  <Award size={15} />
                  <span>Strongest Answer</span>
                </div>
                <blockquote className="answer-quote">"{report.strongest_answer.quote}"</blockquote>
                <p className="answer-why">
                  <strong>Why commanding:</strong> {report.strongest_answer.why_commanding}
                </p>
                {report.strongest_answer.evidence_cited && (
                  <p className="answer-sub">
                    <strong>Evidence cited:</strong> {report.strongest_answer.evidence_cited}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Executive Reframes */}
        {report.executive_reframes && report.executive_reframes.length > 0 && (
          <div className="executive-reframes-section">
            <div className="reframes-heading">
              <Sparkles size={15} className="text-amber-400" />
              <h3>What You Should Have Said</h3>
            </div>
            <div className="reframes-list">
              {report.executive_reframes.map((rf, idx) => (
                <div key={idx} className="reframe-card">
                  <div className="reframe-original">
                    <span className="reframe-tag original">Spoken</span>
                    <p>"{rf.original_quote}"</p>
                  </div>
                  <div className="reframe-replacement">
                    <span className="reframe-tag winning">Executive Reframe</span>
                    <p>"{rf.executive_reframe}"</p>
                  </div>
                  <p className="reframe-rationale">
                    <strong>Tactical Rationale:</strong> {rf.rationale}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Chapters Accordion */}
        {report.chapters && report.chapters.length > 0 && (
          <div className="chapters-container">
            <button
              type="button"
              className="chapters-toggle"
              onClick={() => setShowChapters((prev) => !prev)}
            >
              <span>Debate Chapters ({report.chapters.length} rounds)</span>
              {showChapters ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
            {showChapters && (
              <div className="chapters-list">
                {report.chapters.map((ch) => (
                  <div key={ch.round} className="chapter-item">
                    <div className="chapter-left">
                      <span className="chapter-badge">Round {ch.round}</span>
                      <strong className="chapter-title">{ch.title}</strong>
                      <p className="chapter-summary">{ch.summary}</p>
                    </div>
                    <span className="chapter-score">{ch.score}/100</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Detected Fillers */}
        {detectedFillers.length > 0 && (
          <div className="detected-fillers-row">
            <span className="fillers-label">Detected Fillers:</span>
            <div className="fillers-chips">
              {detectedFillers.map((w, idx) => (
                <span key={`${w}-${idx}`} className="filler-chip">
                  "{w}"
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Weaknesses & Coaching Tips */}
        <div className="report-grid">
          <div>
            <h3>Vulnerabilities Exposed</h3>
            {report.key_weaknesses.map((item, idx) => (
              <p key={idx}>{item}</p>
            ))}
          </div>
          <div>
            <h3>Coaching Recommendations</h3>
            {report.coaching_tips.map((item, idx) => (
              <p key={idx}>{item}</p>
            ))}
          </div>
        </div>

        {/* Close Button */}
        <button type="button" className="primary-action-btn" onClick={onClose}>
          <CheckCircle2 size={16} /> Complete Sparring Session
        </button>
      </section>
    </div>
  );
};
