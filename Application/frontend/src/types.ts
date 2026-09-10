export type ScenarioId =
  | "vc_pitch"
  | "salary_negotiation"
  | "hostile_cross_exam"
  | "custom_debate";

export type Difficulty = "easy" | "medium" | "hard" | "ruthless";
export type AiState = "listening" | "thinking" | "speaking" | "interrupted" | "idle";

export type TranscriptEvent = {
  type: "transcript";
  role: "user" | "ai";
  speaker?: string;
  text: string;
  is_final: boolean;
  confidence?: number;
};

export type InterruptionEvent = {
  type: "interruption";
  by: "user" | "ai";
  latency_ms: number;
  reason: "user_barge_in" | "fluff_detected" | string;
  spoken_before_cut?: string;
  phrase?: string;
};

export type TelemetryEvent = {
  type: "composure_telemetry";
  composure_score: number;
  current_wpm: number;
  filler_word_count: number;
  recent_fillers?: string[];
  hesitation_seconds?: number;
  pressure_level: number;
};

export type AiStateEvent = {
  type: "ai_state";
  state: AiState;
};

export type MicLockEvent = {
  type: "mic_lock";
  locked: boolean;
  reason?: string;
};

export type DebateReportEvent = {
  type: "debate_report";
  overall_score: number;
  verdict: string;
  verdict_description?: string;
  metrics: Record<string, number | string | string[]>;
  key_weaknesses: string[];
  coaching_tips: string[];
};

export type AudioChunkEvent = {
  type: "audio_chunk";
  data: string;
};

export type DebriefStatusEvent = {
  type: "debrief_status";
  status: "generating" | "ready" | "error";
  message?: string;
};

export type ServerEvent =
  | TranscriptEvent
  | InterruptionEvent
  | TelemetryEvent
  | AiStateEvent
  | MicLockEvent
  | DebateReportEvent
  | AudioChunkEvent
  | DebriefStatusEvent
  | { type: "pong" };

export type TranscriptLine = TranscriptEvent & {
  id: string;
  receivedAt: number;
};
