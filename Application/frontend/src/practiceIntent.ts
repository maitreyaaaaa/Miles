import type { ScenarioId } from "./types";
import { scenarios } from "./scenarios";

export type PracticeIntent = { scenario: ScenarioId; topic: string; action: "practice" | "context" | "audio" };
const KEY = "miles_practice_intent";

export function readPracticeIntent(): PracticeIntent | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(KEY) || "null");
    if (!value || !scenarios.some((item) => item.id === value.scenario)) return null;
    return {
      scenario: value.scenario,
      topic: typeof value.topic === "string" ? value.topic.slice(0, 2000) : "",
      action: value.action === "context" || value.action === "audio" ? value.action : "practice",
    };
  } catch { return null; }
}

export function savePracticeIntent(intent: PracticeIntent) {
  sessionStorage.setItem(KEY, JSON.stringify(intent));
}

export function clearPracticeIntent() {
  sessionStorage.removeItem(KEY);
}
