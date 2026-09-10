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
    <div className="w-full max-w-md mx-auto my-2 px-3 py-2 rounded-xl bg-black/30 border border-white/5 backdrop-blur-sm text-xs font-mono select-none">
      <div className="flex items-center justify-between mb-1 text-[11px] text-white/70">
        <span className="flex items-center gap-1.5 font-medium">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          You: <span className="text-white font-semibold">{userPct}%</span>
        </span>
        {hasHesitation && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
            Hesitation &gt;750ms
          </span>
        )}
        <span className="flex items-center gap-1.5 font-medium">
          {opponentName}: <span className="text-white font-semibold">{aiPct}%</span>
          <span className="h-2 w-2 rounded-full bg-sky-400" />
        </span>
      </div>

      <div className="h-1.5 w-full flex rounded-full overflow-hidden bg-white/10">
        <div
          className="h-full bg-emerald-500 transition-all duration-300 ease-out"
          style={{ width: `${userPct}%` }}
        />
        <div
          className="h-full bg-sky-500 transition-all duration-300 ease-out"
          style={{ width: `${aiPct}%` }}
        />
      </div>
    </div>
  );
};
