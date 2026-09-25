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
  speaker_voice?: string;
  is_panel_mode?: boolean;
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
  type: "hesitation" | "ai_cut_in" | "barge_in" | "breakdown" | "fact_verified" | "fact_discrepancy" | "math_contradiction";
  timestamp: number;
  round: number;
  label: string;
  quote?: string;
  why: string;
  reframe?: string;
  latency_ms?: number;
};

export type NumericMetric = {
  name: string;
  raw_value: string;
  numeric_value: number;
  unit: string;
  category: string;
  context: string;
};

export type ContextDossier = {
  context_id: string;
  filename: string;
  doc_type: string;
  title: string;
  executive_summary: string;
  target_role_or_company: string;
  numeric_metrics: NumericMetric[];
  core_claims: string[];
  vulnerabilities: { category: string; issue: string }[];
  cross_exam_traps: string[];
  recommended_scenario: string;
  raw_text_snippet?: string;
  created_at: number;
};

export type FactAuditItem = {
  metric_name: string;
  ground_truth_raw: string;
  ground_truth_val: number;
  user_stated_raw: string;
  user_stated_val: number;
  is_accurate: boolean;
  discrepancy_note: string;
  rectification_salvo: string;
};

export type GroundTruthAudit = {
  has_context: boolean;
  document_title: string;
  document_type: string;
  factual_accuracy_score: number;
  total_audited_metrics: number;
  verified_count: number;
  discrepancy_count: number;
  verified_metrics: FactAuditItem[];
  discrepancies: FactAuditItem[];
  all_ground_truth_metrics: NumericMetric[];
};

export type DebateReportEvent = {
  type: "debate_report";
  session_id?: string;
  share_id?: string;
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
  has_context?: boolean;
  ground_truth_audit?: GroundTruthAudit;
  math_audit?: MathAuditSummary;
  is_panel_mode?: boolean;
  panel?: InterviewerPanel;
};

export type Panelist = {
  id: string;
  name: string;
  title: string;
  role_type: string;
  speaker: string;
  specialty: string;
  prompt_directive?: string;
  fluff_interjections?: string[];
};

export type InterviewerPanel = {
  id: string;
  scenario_id: string;
  title: string;
  description: string;
  panelists: Panelist[];
  opening_panelist_id: string;
  opening_statement: string;
};

export type RhetoricalTactic = {
  id: string;
  name: string;
  description: string;
  hint_phrase: string;
  counter_strategy: string;
};

export type MathDiscrepancyItem = {
  rule_type: string;
  description: string;
  claimed_values: Record<string, any>;
  expected_value: number;
  stated_value: number;
  discrepancy_gap: number;
  lethal_salvo: string;
  round_number: number;
};

export type MathAuditSummary = {
  total_claims_tracked: number;
  math_contradictions_count: number;
  ledger?: Record<string, any>;
  discrepancies: MathDiscrepancyItem[];
};

export type CombatMode = "training_hud" | "blind_combat";

export type PanelInitEvent = {
  type: "panel_init";
  panel: InterviewerPanel;
};

export type RhetoricalTacticEvent = {
  type: "rhetorical_tactic";
  tactic: RhetoricalTactic;
};

export type MathContradictionAlertEvent = {
  type: "math_contradiction_alert";
  rule_type: string;
  description: string;
  lethal_salvo: string;
  claimed_values: Record<string, any>;
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

export type ContextLoadedEvent = {
  type: "context_loaded";
  context_id: string;
  title: string;
  doc_type: string;
  metric_count: number;
  metrics: NumericMetric[];
};

export type FactAuditUpdateEvent = {
  type: "fact_audit_update";
  factual_accuracy_score: number;
  verified_count: number;
  discrepancy_count: number;
  verified_metrics?: FactAuditItem[];
  discrepancies?: FactAuditItem[];
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
  | ContextLoadedEvent
  | FactAuditUpdateEvent
  | PanelInitEvent
  | RhetoricalTacticEvent
  | MathContradictionAlertEvent
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

export type MeetingStatus = 'scheduled' | 'connecting' | 'in_call' | 'completed' | 'failed' | 'cancelled';

export interface MeetingConfig {
  max_duration_seconds: number;
  barge_in_sensitivity: number;
  participant_name: string;
  auto_debrief: boolean;
  audio_only: boolean;
}

export interface MeetingSession {
  meeting_id: string;
  meet_url: string;
  context_id?: string | null;
  context_filename?: string | null;
  persona_id: string;
  difficulty: string;
  topic?: string | null;
  persona_tone?: string | null;
  status: MeetingStatus;
  created_at: number;
  started_at?: number | null;
  ended_at?: number | null;
  duration_seconds: number;
  config: MeetingConfig;
  has_debrief: boolean;
  debrief_report?: DebateReportEvent | null;
  error_message?: string | null;
  provider_mode?: "mock" | "mock_fallback" | "headless" | "external" | "recall_ai" | string;
  provider_notice?: string | null;
  recall_bot_id?: string | null;
  scheduled_join_at?: string | null;
}

export interface RematchConfig {
  id: string;
  scenarioId?: string;
  title: string;
  opponent: string;
  speaker: string;
  trap: string;
  originalQuote: string;
  originalScore: number;
  targetReframe?: string;
  vulnerability?: string;
  sourceType: "weakest_answer" | "moment_replay" | "reframe";
}

export interface RematchEvaluationResult {
  new_score: number;
  original_score: number;
  delta_score: number;
  fillers_before: number;
  fillers_after: number;
  detected_fillers: string[];
  cadence_wpm: number;
  pacing_verdict: string;
  verdict: string;
  adversary_reaction: string;
  tactical_analysis: string;
}


