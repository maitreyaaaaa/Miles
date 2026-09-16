import React from "react";
import type { SpeechIntelligenceEvent } from "../types";

interface DominanceHUDProps {
  intelligence: SpeechIntelligenceEvent | null;
  opponentName: string;
}

export const DominanceHUD: React.FC<DominanceHUDProps> = ({ intelligence, opponentName }) => {
  const userPct = intelligence?.user_pct ?? 50;
  const aiPct = intelligence?.ai_pct ?? 50;
  const hasHesitation = (intelligence?.micro_hesitations?.length ?? 0) > 0;

  return (
    <div className="dominance-hud">
      <div className="dominance-hud-row">
        <span className="dominance-hud-speaker">
          <span className="dominance-dot user" />
          <span>You: <strong style={{ color: "#ffffff" }}>{userPct}%</strong></span>
        </span>
        {hasHesitation && (
          <span className="dominance-hesitation-badge">
            Hesitation &gt;750ms
          </span>
        )}
        <span className="dominance-hud-speaker">
          <span>{opponentName}: <strong style={{ color: "#ffffff" }}>{aiPct}%</strong></span>
          <span className="dominance-dot ai" />
        </span>
      </div>

      <div className="dominance-hud-bar">
        <div
          className="dominance-bar-user"
          style={{ width: `${userPct}%` }}
        />
        <div
          className="dominance-bar-ai"
          style={{ width: `${aiPct}%` }}
        />
      </div>
    </div>
  );
};
