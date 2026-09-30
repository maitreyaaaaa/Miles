import { ArrowRight, FileText, Upload, X } from "lucide-react";
import { useAccessibleDialog } from "../hooks/useAccessibleDialog";
import type { ContextDossier } from "../types";

interface SessionPreparationModalProps {
  isOpen: boolean;
  scenarioLabel: string;
  activeContext: ContextDossier | null;
  onAddContext: () => void;
  onClearContext: () => void;
  onContinue: () => void;
  onClose: () => void;
}

export function SessionPreparationModal({ isOpen, scenarioLabel, activeContext, onAddContext, onClearContext, onContinue, onClose }: SessionPreparationModalProps) {
  const dialogRef = useAccessibleDialog<HTMLDivElement>(isOpen, onClose);
  if (!isOpen) return null;

  return (
    <div className="preflight-overlay" role="presentation" onClick={onClose}>
      <div ref={dialogRef} className="preflight-modal session-preparation-modal" role="dialog" aria-modal="true" aria-labelledby="session-preparation-title" tabIndex={-1} onClick={(event) => event.stopPropagation()}>
        <div className="preflight-header">
          <div className="preflight-titles">
            <p className="session-preparation-step">STEP 1 OF 2 · YOUR MATERIAL</p>
            <h2 id="session-preparation-title">Prepare your sparring session</h2>
            <p>{scenarioLabel}</p>
          </div>
          <button type="button" className="preflight-close-btn" onClick={onClose} aria-label="Cancel session preparation"><X size={18} /></button>
        </div>

        <section className="session-material-card" aria-labelledby="session-material-title">
          <div className="session-material-heading">
            <FileText size={22} aria-hidden="true" />
            <h3 id="session-material-title">Add a pitch deck or notes</h3>
            <span className="session-material-optional">Optional</span>
          </div>
          <p>Miles can use your material to ask specific questions about your claims and numbers. CVs and supporting documents work too.</p>

          {activeContext ? (
            <>
              <div className="session-material-attached" role="status">
                <span>Attached for this session</span>
                <strong>{activeContext.title}</strong>
                <small>{activeContext.numeric_metrics.length} extracted {activeContext.numeric_metrics.length === 1 ? "metric" : "metrics"} · Ready to use</small>
              </div>
              <div className="session-material-actions">
                <button type="button" className="session-material-button" onClick={onAddContext}>Review or replace</button>
                <button type="button" className="session-material-remove" onClick={onClearContext}>Remove document</button>
              </div>
            </>
          ) : (
            <>
              <button type="button" className="session-material-button" onClick={onAddContext}><Upload size={16} aria-hidden="true" /> Add pitch deck or notes</button>
              <small className="session-material-formats">PDF, DOCX, TXT, Markdown or CSV. Export slide decks as PDF.</small>
            </>
          )}
        </section>

        <p className="session-preparation-hint">{activeContext ? "Your document will be included when the session starts." : "No document? You can practice with the scenario alone."} Next, check your microphone and audio.</p>
        <div className="preflight-footer session-preparation-footer">
          <button type="button" className="preflight-skip-btn" onClick={onClose}>Cancel</button>
          <button type="button" className="preflight-submit-btn" onClick={onContinue}>{activeContext ? "Continue to audio check" : "Continue without a document"}<ArrowRight size={16} aria-hidden="true" /></button>
        </div>
      </div>
    </div>
  );
}
