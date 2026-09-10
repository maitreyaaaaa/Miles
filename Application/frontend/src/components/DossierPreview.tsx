import React from "react";
import { AlertCircle, ArrowRight, Crosshair, HelpCircle, ShieldAlert, Swords } from "lucide-react";
import type { BattleDossier } from "../types";

interface DossierPreviewProps {
  dossier: BattleDossier;
  onStart: () => void;
}

export const DossierPreview: React.FC<DossierPreviewProps> = ({ dossier, onStart }) => {
  return (
    <div className="w-full max-w-xl mx-auto mt-4 rounded-2xl border border-white/10 bg-black/40 backdrop-blur-md p-5 text-left text-white shadow-xl animate-fade-in space-y-4">
      {/* Header Badge */}
      <div className="flex items-center justify-between border-b border-white/10 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/10 text-amber-400">
            <Swords className="h-4 w-4" />
          </div>
          <span className="text-xs font-semibold tracking-wider text-amber-400 uppercase">
            5-Vector Battle Dossier
          </span>
        </div>
        <span className="text-xs px-2.5 py-0.5 rounded-full bg-white/5 text-white/60 font-mono">
          Intensity: {dossier.difficulty_profile?.adversarial_intensity || 4}/5
        </span>
      </div>

      {/* Contrarian Thesis */}
      <div className="rounded-xl border border-rose-500/20 bg-rose-500/[0.04] p-3.5 space-y-1">
        <div className="flex items-center gap-2 text-xs font-medium text-rose-400">
          <ShieldAlert className="h-3.5 w-3.5" />
          <span>Contrarian Thesis ({dossier.persona_name || "Adversary"})</span>
        </div>
        <p className="text-sm font-medium text-white/90 leading-snug">
          "{dossier.contrarian_thesis}"
        </p>
      </div>

      {/* Opening Salvo */}
      {dossier.opening_statement && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3 space-y-1">
          <div className="flex items-center gap-2 text-xs font-medium text-white/50">
            <Crosshair className="h-3.5 w-3.5 text-amber-400" />
            <span>Opening Challenge (&lt;25 words)</span>
          </div>
          <p className="text-xs font-mono text-amber-200/90 leading-relaxed">
            "{dossier.opening_statement}"
          </p>
        </div>
      )}

      {/* 5 Attack Vectors */}
      {dossier.attack_vectors && dossier.attack_vectors.length > 0 && (
        <div className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-white/40 flex items-center gap-1.5">
            <Crosshair className="h-3 w-3 text-rose-400" /> Categorized Attack Vectors
          </span>
          <div className="grid grid-cols-1 gap-1.5 text-xs">
            {dossier.attack_vectors.map((vec, idx) => (
              <div
                key={idx}
                className="flex items-start gap-2.5 rounded-lg border border-white/5 bg-white/[0.02] p-2 hover:bg-white/[0.04] transition"
              >
                <span className="mt-0.5 shrink-0 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-white/10 text-white/70">
                  {vec.category}
                </span>
                <span className="text-white/80 leading-tight">{vec.vector}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3 Trap Follow-Up Questions */}
      {dossier.trap_questions && dossier.trap_questions.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-white/40 flex items-center gap-1.5">
            <HelpCircle className="h-3 w-3 text-amber-400" /> Pre-Computed Trap Inquiries
          </span>
          <div className="space-y-1 text-xs">
            {dossier.trap_questions.map((q, idx) => (
              <div key={idx} className="flex items-start gap-2 text-white/70">
                <span className="font-mono text-amber-400 shrink-0">{idx + 1}.</span>
                <span className="italic leading-snug">"{q}"</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Difficulty Calibration & Launch Action */}
      <div className="flex items-center justify-between pt-3 border-t border-white/10">
        <div className="flex items-center gap-2 text-[11px] font-mono text-white/40">
          <span>Max Pause: {dossier.difficulty_profile?.hesitation_threshold_sec || 2.0}s</span>
          <span>•</span>
          <span>Max Monologue: {dossier.difficulty_profile?.rambling_threshold_sec || 10.0}s</span>
        </div>
        <button
          onClick={onStart}
          className="flex items-center gap-1.5 rounded-xl bg-white px-4 py-2 text-xs font-semibold text-black hover:bg-white/90 shadow-lg shadow-white/10 transition"
        >
          <span>Begin Sparring</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};
