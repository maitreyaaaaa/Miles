export type ScenarioId =
  | "vc_pitch"
  | "salary_negotiation"
  | "hostile_cross_exam"
  | "senior_interview"
  | "sales_objections"
  | "media_crisis"
  | "hostile_boardroom"
  | "custom_debate";

export type PersonaTone =
  | "calm_ruthless"
  | "skeptical_vc"
  | "courtroom_aggressive"
  | "cold_negotiator"
  | "smiling_assassin";

export type PersonaToneConfig = {
  id: PersonaTone;
  name: string;
  description: string;
  speaker: string;
};

export type ScenarioDefinition = {
  id: ScenarioId;
  name: string;
  title: string;
  description: string;
  opening_statement: string;
  speaker?: string;
  tags: string[];
  is_custom: boolean;
};

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

export type DebateChapter = {
  round: number;
  title: string;
  summary: string;
  score: number;
};

export type WeakestAnswer = {
  quote: string;
  why_faltered: string;
  vulnerability: string;
};

export type StrongestAnswer = {
  quote: string;
  why_commanding: string;
  evidence_cited: string;
};

export type ExecutiveReframe = {
  original_quote: string;
  executive_reframe: string;
  rationale: string;
};

export type MomentBookmark = {
  id: string;
  type: "hesitation" | "ai_cut_in" | "barge_in" | "breakdown";
  timestamp: number;
  round: number;
  label: string;
  quote?: string;
  why: string;
  reframe?: string;
  latency_ms?: number;
};

export type DebateReportEvent = {
  type: "debate_report";
  session_id?: string;
  scenario?: string;
  topic?: string;
  difficulty?: string;
  rounds_completed?: number;
  overall_score: number;
  verdict: string;
  verdict_description?: string;
  metrics: Record<string, number | string | string[]>;
  key_weaknesses: string[];
  coaching_tips: string[];
  chapters?: DebateChapter[];
  weakest_answer?: WeakestAnswer;
  strongest_answer?: StrongestAnswer;
  executive_reframes?: ExecutiveReframe[];
  bookmarks?: MomentBookmark[];
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

export type MicroHesitation = {
  gap_ms: number;
  word_before: string;
  word_after: string;
  timestamp_ms: number;
  context: string;
  severity: "medium" | "high";
};

export type SpeechIntelligenceEvent = {
  type: "speech_intelligence";
  round: number;
  user_talk_time_sec: number;
  ai_talk_time_sec: number;
  dominance_ratio: number;
  user_pct: number;
  ai_pct: number;
  micro_hesitations?: MicroHesitation[];
  confidence_mean?: number;
  stress_indicator?: string;
};

export type TurnTelemetryEvent = {
  type: "turn_telemetry";
  ttfa_ms: number;
  barge_in_latency_ms: number;
  stt_provider: string;
  tts_provider: string;
  llm_provider: string;
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
  | SpeechIntelligenceEvent
  | TurnTelemetryEvent
  | { type: "pong" };

export type TranscriptLine = TranscriptEvent & {
  id: string;
  receivedAt: number;
};

export type PreflightResponse = {
  backend_status: string;
  assemblyai_status: string;
  assemblyai_model: string;
  rime_status: string;
  rime_model: string;
  rime_speaker: string;
  active_llm: string;
};

export type AttackVector = {
  category: string;
  vector: string;
};

export type ScoringRubric = {
  evidence_weight: number;
  cadence_weight: number;
  composure_weight: number;
  brevity_weight: number;
};

export type DifficultyProfile = {
  hesitation_threshold_sec: number;
  rambling_threshold_sec: number;
  filler_tolerance: number;
  adversarial_intensity: number;
};

export type BattleDossier = {
  scenario_id: string;
  topic: string;
  persona_name: string;
  contrarian_thesis: string;
  opening_statement: string;
  attack_vectors: AttackVector[];
  trap_questions: string[];
  scoring_rubric: ScoringRubric;
  difficulty_profile: DifficultyProfile;
};


