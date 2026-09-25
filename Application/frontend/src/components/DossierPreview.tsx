import React from "react";
import { AlertCircle, ArrowRight, Crosshair, HelpCircle, ShieldAlert, Swords } from "lucide-react";
import type { BattleDossier } from "../types";
import DecryptedText from "./DecryptedText";

interface DossierPreviewProps {
  dossier: BattleDossier;
  onStart: () => void;
}

export const DossierPreview: React.FC<DossierPreviewProps> = ({ dossier, onStart }) => {
  return (
    <div className="dossier-card">
      {/* Header Badge */}
      <div className="dossier-header">
        <div className="dossier-badge">
          <div className="dossier-badge-icon">
            <Swords size={16} />
          </div>
          <span>Prep Brief & Strategy Breakdown</span>
        </div>
        <span className="dossier-intensity-pill">
          Intensity: {dossier.difficulty_profile?.adversarial_intensity || 4}/5
        </span>
      </div>

      {/* Contrarian Thesis */}
      <div className="dossier-thesis-box">
        <div className="dossier-thesis-label">
          <ShieldAlert size={14} />
          <span>Opposing Viewpoint ({dossier.persona_name ? <DecryptedText text={dossier.persona_name} speed={30} maxIterations={8} animateOn="view" /> : "Adversary"})</span>
        </div>
        <p className="dossier-thesis-text">
          "{dossier.contrarian_thesis}"
        </p>
      </div>

      {/* Opening Salvo */}
      {dossier.opening_statement && (
        <div className="dossier-opening-box">
          <div className="dossier-opening-label">
            <Crosshair size={14} />
            <span>Opening Challenge (&lt;25 words)</span>
          </div>
          <p className="dossier-opening-text">
            "{dossier.opening_statement}"
          </p>
        </div>
      )}

      {/* 5 Attack Vectors */}
      {dossier.attack_vectors && dossier.attack_vectors.length > 0 && (
        <div className="dossier-section">
          <span className="dossier-section-title">
            <Crosshair size={13} style={{ color: "#fb7185" }} /> Key Angles & Pushbacks
          </span>
          <div className="dossier-vectors-list">
            {dossier.attack_vectors.map((vec, idx) => (
              <div key={idx} className="dossier-vector-item">
                <span className="dossier-vector-cat">
                  {vec.category}
                </span>
                <span className="dossier-vector-content">{vec.vector}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3 Trap Follow-Up Questions */}
      {dossier.trap_questions && dossier.trap_questions.length > 0 && (
        <div className="dossier-section">
          <span className="dossier-section-title">
            <HelpCircle size={13} style={{ color: "#fbbf24" }} /> Likely Follow-up Traps
          </span>
          <div className="dossier-traps-list">
            {dossier.trap_questions.map((q, idx) => (
              <div key={idx} className="dossier-trap-item">
                <span className="dossier-trap-num">{idx + 1}.</span>
                <span className="dossier-trap-text">"{q}"</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Difficulty Calibration & Launch Action */}
      <div className="dossier-footer">
        <div className="dossier-thresholds">
          <span>Max Pause: {dossier.difficulty_profile?.hesitation_threshold_sec || 2.0}s</span>
          <span>•</span>
          <span>Max Monologue: {dossier.difficulty_profile?.rambling_threshold_sec || 10.0}s</span>
        </div>
        <button
            type="button"
            onClick={onStart}
            className="dossier-start-btn"
          >
            <span>Start Sparring</span>
            <ArrowRight size={14} />
          </button>
      </div>
    </div>
  );
};
