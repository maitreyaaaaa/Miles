import type { ScenarioId } from "./types";

export const scenarios: { id: ScenarioId; label: string; opponent: string; topic: string; tag: string }[] = [
  {
    id: "vc_pitch",
    label: "VC Pitch",
    opponent: "Marcus Vance",
    topic: "Defend your startup's market, moat, and unit economics.",
    tag: "Startups",
  },
  {
    id: "salary_negotiation",
    label: "Salary Negotiation",
    opponent: "Elena Rostova",
    topic: "Negotiate compensation against a hardball VP of Talent.",
    tag: "Career",
  },
  {
    id: "hostile_cross_exam",
    label: "Cross-Examination",
    opponent: "DA Carter",
    topic: "Handle sharp, aggressive questions without contradicting yourself.",
    tag: "Legal",
  },
  {
    id: "senior_interview",
    label: "Systems Architecture",
    opponent: "David Chen",
    topic: "Defend distributed consensus and scale tradeoffs under scrutiny.",
    tag: "Engineering",
  },
  {
    id: "sales_objections",
    label: "Enterprise Sales",
    opponent: "Victoria Vance",
    topic: "Overcome procurement pushback, ROI skepticism, and contract risk.",
    tag: "Sales",
  },
  {
    id: "media_crisis",
    label: "Media Crisis",
    opponent: "Sarah Jenkins",
    topic: "Handle hostile investigative questioning on an executive leak.",
    tag: "PR",
  },
  {
    id: "hostile_boardroom",
    label: "Activist Boardroom",
    opponent: "Arthur Sterling",
    topic: "Defend operating margins and strategy against activist investors.",
    tag: "Leadership",
  },
  {
    id: "custom_debate",
    label: "Custom Topic",
    opponent: "The Contrarian",
    topic: "Pick any stance and defend it under real counter-pressure.",
    tag: "Freeform",
  },
];
