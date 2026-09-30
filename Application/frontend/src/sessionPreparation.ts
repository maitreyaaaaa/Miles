export type PreparationStep = "idle" | "materials" | "upload" | "audio";
export type PreparationAction = "prepare" | "upload" | "documentClosed" | "continue" | "confirm" | "cancel";

// Document analysis never starts a voice session. Audio checks must still pass.
export function sessionPreparationReducer(step: PreparationStep, action: PreparationAction): PreparationStep {
  switch (action) {
    case "prepare": return step === "idle" ? "materials" : step;
    case "upload": return step === "materials" ? "upload" : step;
    case "documentClosed": return step === "upload" ? "materials" : step;
    case "continue": return step === "materials" ? "audio" : step;
    case "confirm": return step === "audio" ? "idle" : step;
    case "cancel": return "idle";
  }
}
