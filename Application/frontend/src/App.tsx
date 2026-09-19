import { ArrowLeft, ArrowRight, CircleStop, FileCheck, Mic, MicOff, RotateCcw, ShieldCheck, Video } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MicrophoneStreamer, VoicePlayer } from "./audio";
import { PreflightModal } from "./components/PreflightModal";
import { DossierPreview } from "./components/DossierPreview";
import { DominanceHUD } from "./components/DominanceHUD";
import { DebriefModal } from "./components/DebriefModal";
import { ContextUploadModal } from "./components/ContextUploadModal";
import { MeetingSchedulerModal } from "./components/MeetingSchedulerModal";
import { MarketingLanding } from "./components/MarketingLanding";
import RubberSegment from "./components/RubberSegment";
import ShinyText from "./components/ShinyText";
import DecryptedText from "./components/DecryptedText";
import type {
  AiState,
  BattleDossier,
  ContextDossier,
  DebateReportEvent,
  Difficulty,
  InterruptionEvent,
  PersonaTone,
  ScenarioId,
  ServerEvent,
  SpeechIntelligenceEvent,
  TelemetryEvent,
  TranscriptLine,
  TurnTelemetryEvent,
} from "./types";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8000";

const scenarios: { id: ScenarioId; label: string; opponent: string; topic: string; tag: string }[] = [
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
    topic: "Survive a courtroom-style attack on your consistency.",
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
    topic: "Write any position and argue it under relentless counter-pressure.",
    tag: "Freeform",
  },
];

const personaTones: { id: PersonaTone; label: string; desc: string }[] = [
  { id: "calm_ruthless", label: "Calm Ruthless", desc: "Icy clinical precision" },
  { id: "skeptical_vc", label: "Skeptical VC", desc: "Impatient & numbers-obsessed" },
  { id: "courtroom_aggressive", label: "Courtroom Aggressive", desc: "Rapid-fire cross-exam" },
  { id: "cold_negotiator", label: "Cold Negotiator", desc: "Immovable & low anchoring" },
  { id: "smiling_assassin", label: "Smiling Assassin", desc: "Polite with lethal traps" },
];

const difficulties: Difficulty[] = ["easy", "medium", "hard", "ruthless"];
const thinkingWords = [
  "apophenia",
  "palimpsest",
  "susurrus",
  "liminality",
  "aporia",
  "numinous",
  "sonder",
  "quincunx",
];

type TopicPrep =
  | { status: "idle"; word: string }
  | { status: "thinking"; word: string }
  | {
      status: "ready";
      word: string;
      dossier: BattleDossier;
    }
  | { status: "error"; word: string; message: string };

const initialTelemetry: TelemetryEvent = {
  type: "composure_telemetry",
  composure_score: 100,
  current_wpm: 0,
  filler_word_count: 0,
  recent_fillers: [],
  hesitation_seconds: 0,
  pressure_level: 1,
};

function buildWsUrl(
  scenario: ScenarioId,
  difficulty: Difficulty,
  topic: string,
  personaTone: PersonaTone,
  contextId?: string,
) {
  const base = new URL(BACKEND_URL);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = "/ws/debate";
  base.search = "";
  base.searchParams.set("scenario", scenario);
  base.searchParams.set("difficulty", difficulty);
  base.searchParams.set("persona_tone", personaTone);
  base.searchParams.set("audio_format", "binary");
  if (scenario === "custom_debate" && topic.trim()) {
    base.searchParams.set("topic", topic.trim());
  }
  if (contextId) {
    base.searchParams.set("context_id", contextId);
  }
  return base.toString();
}

function App() {
  const [hasStarted, setHasStarted] = useState(false);
  const [scenario, setScenario] = useState<ScenarioId>("vc_pitch");
  const [difficulty, setDifficulty] = useState<Difficulty>("hard");
  const [personaTone, setPersonaTone] = useState<PersonaTone>("calm_ruthless");
  const [topic, setTopic] = useState("");
  const [connection, setConnection] = useState<"offline" | "connecting" | "live">("offline");
  const [aiState, setAiState] = useState<AiState>("idle");
  const [micActive, setMicActive] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [isMicLocked, setIsMicLocked] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptLine[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryEvent>(initialTelemetry);
  const [lastInterruption, setLastInterruption] = useState<InterruptionEvent | null>(null);
  const [interruptionCount, setInterruptionCount] = useState(0);
  const [report, setReport] = useState<DebateReportEvent | null>(null);
  const [debriefLoading, setDebriefLoading] = useState(false);
  const [debriefMessage, setDebriefMessage] = useState("Analyzing debate transcript with GPT-4o...");
  const [statusText, setStatusText] = useState("ready");
  const [topicPrep, setTopicPrep] = useState<TopicPrep>({ status: "idle", word: "ready" });
  const [aiSubtitle, setAiSubtitle] = useState<{
    text: string;
    isFinal: boolean;
    speaker?: string;
    interrupted?: boolean;
  } | null>(null);
  const [showPreflight, setShowPreflight] = useState(false);
  const [pendingStart, setPendingStart] = useState(false);
  const [activeContext, setActiveContext] = useState<ContextDossier | null>(null);
  const [showContextModal, setShowContextModal] = useState(false);
  const [showMeetingModal, setShowMeetingModal] = useState(false);
  const [speechIntel, setSpeechIntel] = useState<SpeechIntelligenceEvent | null>(null);
  const [turnTelemetry, setTurnTelemetry] = useState<TurnTelemetryEvent | null>(null);

  const [currentView, setCurrentView] = useState<"marketing" | "arena">(() => {
    return typeof window !== "undefined" && window.location.hash === "#arena" ? "arena" : "marketing";
  });

  useEffect(() => {
    const handleHashChange = () => {
      if (window.location.hash === "#arena") {
        setCurrentView("arena");
      } else {
        setCurrentView("marketing");
      }
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const handleStartFromMarketing = (selectedScenario?: ScenarioId, customTopic?: string) => {
    if (selectedScenario) {
      setScenario(selectedScenario);
    }
    if (customTopic !== undefined) {
      setTopic(customTopic);
      if (customTopic.trim()) {
        setScenario("custom_debate");
      }
    }
    setCurrentView("arena");
    window.location.hash = "#arena";
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleBackToMarketing = () => {
    setCurrentView("marketing");
    window.location.hash = "";
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const wsRef = useRef<WebSocket | null>(null);
  const playerRef = useRef<VoicePlayer | null>(null);
  const micRef = useRef<MicrophoneStreamer | null>(null);

  const activeScenario = useMemo(
    () => scenarios.find((item) => item.id === scenario) ?? scenarios[0],
    [scenario],
  );

  const stopMic = useCallback(() => {
    micRef.current?.stop();
    micRef.current = null;
    setMicActive(false);
    setMicLevel(0);
    setIsMicLocked(false);
  }, []);

  const disconnect = useCallback(() => {
    stopMic();
    wsRef.current?.close();
    wsRef.current = null;
    playerRef.current?.stopImmediately();
    setIsMicLocked(false);
    setConnection("offline");
    setAiState("idle");
    setStatusText("ready");
  }, [stopMic]);

  useEffect(() => {
    return () => {
      stopMic();
      wsRef.current?.close();
      void playerRef.current?.close();
    };
  }, [stopMic]);

  useEffect(() => {
    const trimmed = topic.trim();
    if (!trimmed) {
      setTopicPrep({ status: "idle", word: "ready" });
      return;
    }

    const controller = new AbortController();
    setTopicPrep({ status: "thinking", word: thinkingWords[0] });

    const timeout = window.setTimeout(async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/scenarios/custom`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic: trimmed, difficulty, persona_tone: personaTone }),
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Custom topic failed with ${response.status}`);
        }

        const payload = (await response.json()) as BattleDossier;

        setTopicPrep({
          status: "ready",
          word: "calibrated",
          dossier: payload,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setTopicPrep({
          status: "error",
          word: "interrupted",
          message: error instanceof Error ? error.message : "Topic preparation failed",
        });
      }
    }, 520);

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [difficulty, personaTone, topic]);

  useEffect(() => {
    if (topicPrep.status !== "thinking") return;

    let index = 0;
    const interval = window.setInterval(() => {
      index = (index + 1) % thinkingWords.length;
      setTopicPrep((current) => (
        current.status === "thinking"
          ? { ...current, word: thinkingWords[index] }
          : current
      ));
    }, 680);

    return () => window.clearInterval(interval);
  }, [topicPrep.status]);

  const handleEvent = useCallback(async (event: ServerEvent) => {
    switch (event.type) {
      case "transcript":
        setTranscripts((current) => [
          ...current,
          { ...event, id: crypto.randomUUID(), receivedAt: Date.now() },
        ].slice(-80));

        if (event.role === "ai") {
          setAiSubtitle({
            text: event.text,
            isFinal: event.is_final,
            speaker: event.speaker || activeScenario.opponent,
            interrupted: false,
          });
        }

        if (event.is_final) {
          // Final transcript line received
        }
        break;
      case "interruption":
        setLastInterruption(event);
        setInterruptionCount((count) => count + 1);
        if (event.by === "user") {
          playerRef.current?.stopImmediately();
          setAiState("interrupted");
          setAiSubtitle((prev) =>
            prev ? { ...prev, text: event.spoken_before_cut || prev.text, interrupted: true } : null
          );
        } else if (event.by === "ai") {
          // Adversarial interjection: AI seizes conversational floor
          micRef.current?.setMuted(true);
          setIsMicLocked(true);
          setAiState("speaking");
          setAiSubtitle({
            text: event.phrase || event.spoken_before_cut || "Hold on...",
            isFinal: true,
            speaker: activeScenario.opponent,
            interrupted: false,
          });
        }
        break;
      case "mic_lock":
        micRef.current?.setMuted(event.locked);
        setIsMicLocked(event.locked);
        break;
      case "composure_telemetry":
        setTelemetry(event);
        break;
      case "ai_state":
        setAiState(event.state);
        if (event.state === "speaking") {
          playerRef.current?.resetPlayback();
        } else if (event.state === "listening") {
          micRef.current?.setMuted(false);
          setIsMicLocked(false);
        }
        break;
      case "debrief_status":
        if (event.status === "generating") {
          setDebriefLoading(true);
          if (event.message) setDebriefMessage(event.message);
        } else if (event.status === "error") {
          setDebriefLoading(false);
        }
        break;
      case "debate_report":
        setDebriefLoading(false);
        setReport(event);
        break;
      case "audio_chunk":
        await playerRef.current?.playBase64Chunk(event.data);
        break;
      case "speech_intelligence":
        setSpeechIntel(event);
        break;
      case "turn_telemetry":
        setTurnTelemetry(event);
        break;
      case "pong":
        break;
    }
  }, [activeScenario.opponent]);

  const openSession = useCallback(async (sessionScenario: ScenarioId) => {
    disconnect();
    setConnection("connecting");
    setStatusText("connecting");
    setReport(null);
    setLastInterruption(null);
    setInterruptionCount(0);
    setTranscripts([]);
    setAiSubtitle(null);
    setTelemetry(initialTelemetry);
    setSpeechIntel(null);
    setTurnTelemetry(null);
    setDebriefLoading(false);

    playerRef.current = new VoicePlayer(22050);
    try {
      await playerRef.current.unlock();
    } catch {
      setStatusText("audio blocked");
    }
    const socket = new WebSocket(buildWsUrl(sessionScenario, difficulty, topic, personaTone, activeContext?.context_id));
    socket.binaryType = "arraybuffer";
    wsRef.current = socket;

    socket.onopen = () => {
      setConnection("live");
      setStatusText("live");
    };

    socket.onmessage = async (message) => {
      if (message.data instanceof ArrayBuffer) {
        await playerRef.current?.playChunk(message.data);
        return;
      }
      if (message.data instanceof Blob) {
        await playerRef.current?.playChunk(await message.data.arrayBuffer());
        return;
      }
      try {
        await handleEvent(JSON.parse(message.data) as ServerEvent);
      } catch {
        setStatusText("event skipped");
      }
    };

    socket.onerror = () => {
      setStatusText("connection error");
      setConnection("offline");
    };

    socket.onclose = () => {
      stopMic();
      setConnection("offline");
      setAiState("idle");
      setStatusText("closed");
    };
  }, [activeContext, difficulty, disconnect, handleEvent, personaTone, stopMic, topic]);

  const startDebate = async () => {
    const selectedScenario = topic.trim() ? "custom_debate" : scenario;
    setScenario(selectedScenario);

    if (sessionStorage.getItem("miles_preflight_passed") !== "true") {
      setPendingStart(true);
      setShowPreflight(true);
      return;
    }

    setHasStarted(true);
    await openSession(selectedScenario);
  };

  const handlePreflightConfirm = async () => {
    setShowPreflight(false);
    if (pendingStart) {
      setPendingStart(false);
      const selectedScenario = topic.trim() ? "custom_debate" : scenario;
      setHasStarted(true);
      await openSession(selectedScenario);
    }
  };

  const handlePreflightClose = () => {
    setPendingStart(false);
    setShowPreflight(false);
  };

  const toggleMic = async () => {
    const socket = wsRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;

    if (micActive) {
      stopMic();
      return;
    }

    const mic = new MicrophoneStreamer();
    micRef.current = mic;
    await mic.start(socket, setMicLevel);
    await playerRef.current?.ensureRunning();
    setMicActive(true);
  };

  const endDebate = () => {
    stopMic();
    playerRef.current?.stopImmediately();
    setDebriefLoading(true);
    setDebriefMessage("Analyzing debate transcript with GPT-4o...");
    wsRef.current?.send(JSON.stringify({ type: "end_debate" }));
  };

  const returnHome = () => {
    disconnect();
    setHasStarted(false);
    setDebriefLoading(false);
    setTranscripts([]);
    setReport(null);
    setLastInterruption(null);
    setInterruptionCount(0);
    setAiSubtitle(null);
    setSpeechIntel(null);
    setTurnTelemetry(null);
  };

  if (!hasStarted) {
    if (currentView === "marketing") {
      return (
        <main className="marketing-view-shell">
          <MarketingLanding
            onStartDebate={handleStartFromMarketing}
            onOpenPreflight={() => setShowPreflight(true)}
            onOpenContextModal={() => setShowContextModal(true)}
            onOpenMeetModal={() => setShowMeetingModal(true)}
          />

          <PreflightModal
            isOpen={showPreflight}
            onClose={handlePreflightClose}
            onConfirm={handlePreflightConfirm}
            backendUrl={BACKEND_URL}
          />
          <ContextUploadModal
            isOpen={showContextModal}
            onClose={() => setShowContextModal(false)}
            activeContext={activeContext}
            onSelectContext={(dossier) => setActiveContext(dossier)}
            onClearContext={() => setActiveContext(null)}
            backendUrl={BACKEND_URL}
          />
          <MeetingSchedulerModal
            isOpen={showMeetingModal}
            onClose={() => setShowMeetingModal(false)}
            activeContext={activeContext}
            backendUrl={BACKEND_URL}
            onOpenContextUpload={() => {
              setShowMeetingModal(false);
              setShowContextModal(true);
            }}
            onViewDebrief={(debriefReport) => {
              setReport(debriefReport);
            }}
          />
        </main>
      );
    }

    return (
      <main className="arena-view-shell">
        {/* TOP ARENA NAVIGATION */}
        <header className="arena-top-nav">
          <div className="arena-nav-left">
            <button
              type="button"
              className="arena-back-btn"
              onClick={handleBackToMarketing}
              title="Return to marketing overview"
            >
              <ArrowLeft size={15} />
              <span>Overview</span>
            </button>
            <div className="arena-brand-link" onClick={handleBackToMarketing}>
              <img src="/miles_home_logo.png" alt="Miles" className="arena-nav-logo" />
            </div>
          </div>
          <div className="arena-nav-right">
            <button
              type="button"
              className="arena-nav-pill"
              onClick={() => setShowPreflight(true)}
            >
              <ShieldCheck size={14} />
              <span>Audio Setup</span>
            </button>
            <button
              type="button"
              className={`arena-nav-pill ${activeContext ? "active-pill" : ""}`}
              onClick={() => setShowContextModal(true)}
            >
              <FileCheck size={14} />
              <span>{activeContext ? "Deck Armed" : "Attach Deck"}</span>
            </button>
            <button
              type="button"
              className="arena-nav-pill meet-pill"
              onClick={() => setShowMeetingModal(true)}
            >
              <Video size={14} />
              <span>Google Meet</span>
            </button>
          </div>
        </header>

        {/* ARENA INTRO BANNER */}
        <div className="arena-hero-banner">
          <div className="arena-badge-pill">
            <ShinyText text="Verbal Sparring Arena" speed={4} />
          </div>
          <h1 className="arena-title">Calibrate your adversary & combat rules</h1>
          <p className="arena-subtitle">
            Choose an adversarial archetype or write your own thesis. All matches stream full-duplex with real-time cadence and composure HUD.
          </p>
        </div>

        {/* Active Context Banner */}
        {activeContext && (
          <div style={{ display: "flex", justifyContent: "center", padding: "16px 24px 0", background: "#ffffff" }}>
            <div className="hero-context-banner" style={{ margin: 0 }}>
              <div className="context-banner-left">
                <span className="context-banner-type">{activeContext.doc_type.replace("_", " ").toUpperCase()}</span>
                <strong>{activeContext.title}</strong>
                <span className="context-banner-metrics">({activeContext.numeric_metrics.length} metrics tracked)</span>
              </div>
              <div className="context-banner-actions">
                <button type="button" onClick={() => setShowContextModal(true)}>
                  Inspect
                </button>
                <button type="button" onClick={() => setActiveContext(null)}>
                  Remove
                </button>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 2: WHITE BACKGROUND CONTENT & ADVANCED CONTROLS */}
        <section className="white-content-section" aria-label="Debate Configuration">
          <div className="white-content-inner">
            {/* Topic Maker Input Capsule */}
            <div className="hero-topic-maker" style={{ margin: "0 auto 16px" }}>
              <label htmlFor="custom-topic" className="hero-topic-label">
                Argue your own thesis
              </label>
              <form
                className="hero-topic-capsule"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (topic.trim() && topicPrep.status !== "thinking") {
                    startDebate();
                  }
                }}
              >
                <input
                  id="custom-topic"
                  value={topic}
                  onChange={(event) => {
                    setTopic(event.target.value);
                    if (event.target.value.trim()) setScenario("custom_debate");
                  }}
                  placeholder="e.g. Remote work is better than office work"
                />
                <button
                  type="submit"
                  className="hero-topic-arrow-btn"
                  title="Spar on this topic"
                  disabled={topicPrep.status === "thinking"}
                >
                  <ArrowRight size={16} />
                </button>
              </form>

              {topic.trim() && (
                <div className={`topic-prep ${topicPrep.status}`}>
                  {topicPrep.status === "thinking" && (
                    <div className="topic-prep-thinking-box">
                      <span className="animate-pulse">Cognitive calibration:</span>
                      <strong>{topicPrep.word}</strong>
                    </div>
                  )}
                  {topicPrep.status === "ready" && topicPrep.dossier && (
                    <DossierPreview dossier={topicPrep.dossier} onStart={startDebate} />
                  )}
                  {topicPrep.status === "error" && (
                    <p>{topicPrep.message}</p>
                  )}
                </div>
              )}
            </div>

            <div className="section-divider-badge-wrapper">
              <span className="section-eyebrow-badge">SPARRING ARCHETYPES</span>
              <h2 className="section-heading-clean">Select your opponent</h2>
              <p className="section-subheading-clean">
                Explore specialized scenarios or adjust tactical aggression and difficulty.
              </p>
            </div>

            {/* All Scenarios */}
            <div className="control-group-box">
              <div className="section-label">All Scenarios</div>
              <div className="predefined-topics" aria-label="Predefined topics">
                {scenarios
                  .filter((item) => item.id !== "custom_debate")
                  .map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={scenario === item.id && !topic.trim() ? "selected" : ""}
                      onClick={() => {
                        setScenario(item.id);
                        setTopic("");
                      }}
                    >
                      <span className="scenario-tag-badge">{item.tag}</span>
                      <span className="scenario-title-bold">{scenario === item.id && !topic.trim() ? <DecryptedText text={item.label} animateOn="view" speed={35} maxIterations={8} /> : item.label}</span>
                      <small>{item.topic}</small>
                    </button>
                  ))}
              </div>
            </div>

            {/* Adversary Persona Tone */}
            <div className="control-group-box">
              <div className="section-label">Adversary Persona Tone</div>
              <div className="segmented-control-wrapper">
                <RubberSegment
                  items={personaTones.map((item) => ({
                    value: item.id,
                    label: item.label,
                    title: item.desc,
                  }))}
                  value={personaTone}
                  onChange={(val) => setPersonaTone(val as PersonaTone)}
                  equalSlots={false}
                  trackColor="#f4f4f5"
                  thumbColor="#0a0a0a"
                  textColor="#52525b"
                  activeTextColor="#ffffff"
                  size="md"
                  radius={999}
                  inset={3}
                  stretch={50}
                  squash={3}
                  speed={1}
                  glide={75}
                  draggable
                  aria-label="Adversary Persona Tone"
                />
              </div>
            </div>

            {/* Sparring Intensity */}
            <div className="control-group-box">
              <div className="section-label">Sparring Intensity</div>
              <div className="segmented-control-wrapper">
                <RubberSegment
                  items={difficulties.map((item) => ({
                    value: item,
                    label: item.charAt(0).toUpperCase() + item.slice(1),
                  }))}
                  value={difficulty}
                  onChange={(val) => setDifficulty(val as Difficulty)}
                  equalSlots={true}
                  trackColor="#f4f4f5"
                  thumbColor="#0a0a0a"
                  textColor="#52525b"
                  activeTextColor="#ffffff"
                  size="md"
                  radius={999}
                  inset={3}
                  stretch={80}
                  squash={3}
                  speed={1}
                  glide={75}
                  draggable
                  aria-label="Sparring Intensity"
                />
              </div>
            </div>

            {/* Bottom Quick Start CTA */}
            <div className="white-section-cta">
              <button
                  className="hero-start-cta"
                  type="button"
                  onClick={startDebate}
                  disabled={topicPrep.status === "thinking"}
                >
                  {topicPrep.status === "thinking" ? "Preparing..." : "Start debate"}
                </button>
            </div>
          </div>
        </section>

        <PreflightModal
          isOpen={showPreflight}
          onClose={handlePreflightClose}
          onConfirm={handlePreflightConfirm}
          backendUrl={BACKEND_URL}
        />
        <ContextUploadModal
          isOpen={showContextModal}
          onClose={() => setShowContextModal(false)}
          activeContext={activeContext}
          onSelectContext={(dossier) => setActiveContext(dossier)}
          onClearContext={() => setActiveContext(null)}
          backendUrl={BACKEND_URL}
        />
        <MeetingSchedulerModal
          isOpen={showMeetingModal}
          onClose={() => setShowMeetingModal(false)}
          activeContext={activeContext}
          backendUrl={BACKEND_URL}
          onOpenContextUpload={() => {
            setShowMeetingModal(false);
            setShowContextModal(true);
          }}
          onViewDebrief={(debriefReport) => {
            setReport(debriefReport);
          }}
        />
      </main>
    );
  }

  return (
    <main className="debate-shell">
      <header className="debate-header">
        <Logo compact />
        <div className="live-meta">
          <span>{activeScenario.label}</span>
          <span>{difficulty}</span>
          <span>{statusText}</span>
          <button
            type="button"
            className="preflight-trigger-btn"
            onClick={() => setShowPreflight(true)}
            title="Audio & Voice Calibration"
            style={{ padding: "3px 10px", fontSize: "0.72rem" }}
          >
            <ShieldCheck size={11} /> Audio Setup
          </button>
        </div>
        <button className="ghost-icon" type="button" title="Back to start" onClick={returnHome}>
          <RotateCcw size={18} aria-hidden="true" />
        </button>
      </header>

      <section className="live-stage">
        <DominanceHUD intelligence={speechIntel} opponentName={activeScenario.opponent} />
        {lastInterruption && (
          <p className={`interruption-line ${lastInterruption.by === "ai" ? "ai-cut" : "user-barge"}`}>
            {lastInterruption.by === "user" ? "User Barge-in" : "Adversary Interruption"} {lastInterruption.latency_ms.toFixed(2)} ms
            {lastInterruption.reason && ` • ${lastInterruption.reason.replace(/_/g, " ")}`}
          </p>
        )}
        <div className={`presence ${aiState} ${isMicLocked ? "adversary-active" : ""}`}>
          <div className="blob-wrap" aria-hidden="true">
            <div className="blob-shadow" />
            <div className="voice-blob">
              <span />
              <span />
              <span />
            </div>
            <div className="listen-ring" />
            <div className="listen-ring delay" />
          </div>
          <p>{activeScenario.opponent}</p>
          <strong>{isMicLocked ? "interjecting" : aiState === "speaking" ? "speaking" : aiState === "thinking" ? "thinking" : "listening"}</strong>
        </div>

        {/* Live AI Spoken Subtitles */}
        {aiSubtitle && (
          <div
            className={`ai-subtitles ${aiState === "speaking" ? "speaking" : ""} ${
              aiSubtitle.interrupted ? "interrupted" : ""
            } ${isMicLocked ? "adversary-cut" : ""}`}
          >
            <div className="subtitles-meta">
              <span className="speaker-name">{aiSubtitle.speaker || activeScenario.opponent}</span>
              {aiSubtitle.interrupted ? (
                <span className="tag interrupted">Interrupted</span>
              ) : isMicLocked ? (
                <span className="tag adversary-cut">Adversary Interjection</span>
              ) : !aiSubtitle.isFinal ? (
                <span className="tag streaming">Speaking</span>
              ) : null}
            </div>
            <p className="subtitles-body">"{aiSubtitle.text}"</p>
          </div>
        )}
      </section>

      <footer className="minimal-dock">
        <button
          className={`mic-button ${micActive ? "recording" : ""} ${isMicLocked ? "locked" : ""}`}
          type="button"
          title={
            isMicLocked
              ? "Adversary speaking — Microphone temporarily locked"
              : micActive
              ? "Stop microphone"
              : "Start microphone"
          }
          onClick={toggleMic}
          disabled={connection !== "live" || debriefLoading || isMicLocked}
        >
          {isMicLocked ? <MicOff size={20} /> : micActive ? <MicOff size={20} /> : <Mic size={20} />}
          <span style={{ "--level": isMicLocked ? 0 : micLevel } as React.CSSProperties} />
        </button>
        {isMicLocked && (
          <div className="mic-lock-notice">
            <span className="lock-dot" />
            <span>Adversary Speaking — Listen</span>
          </div>
        )}
        <button
          className={`debrief-button ${debriefLoading ? "loading" : ""}`}
          type="button"
          onClick={endDebate}
          disabled={connection !== "live" || debriefLoading}
        >
          <CircleStop size={18} aria-hidden="true" />
          {debriefLoading ? "Analyzing..." : "Debrief"}
        </button>
      </footer>

      {debriefLoading && (
        <div className="modal-backdrop" role="presentation">
          <section className="debrief-loading-card" role="dialog" aria-modal="true" aria-label="Evaluating debate">
            <div className="debrief-spinner" />
            <h2>Evaluating Debate Transcript</h2>
            <p className="debrief-loading-model">Powered by GPT-4o</p>
            <p className="debrief-loading-sub">{debriefMessage}</p>
            <div className="debrief-loading-tags">
              <span>Checking filler words</span>
              <span>•</span>
              <span>Measuring cadence & pacing</span>
              <span>•</span>
              <span>Auditing argument defensibility</span>
            </div>
          </section>
        </div>
      )}

      {report && !debriefLoading && (
        <DebriefModal
          report={report}
          telemetry={telemetry}
          transcriptCount={transcripts.filter((line) => line.is_final).length}
          interruptions={interruptionCount}
          onClose={() => setReport(null)}
        />
      )}
      <PreflightModal
        isOpen={showPreflight}
        onClose={handlePreflightClose}
        onConfirm={handlePreflightConfirm}
        backendUrl={BACKEND_URL}
      />
      <ContextUploadModal
        isOpen={showContextModal}
        onClose={() => setShowContextModal(false)}
        activeContext={activeContext}
        onSelectContext={(dossier) => setActiveContext(dossier)}
        onClearContext={() => setActiveContext(null)}
        backendUrl={BACKEND_URL}
      />
      <MeetingSchedulerModal
        isOpen={showMeetingModal}
        onClose={() => setShowMeetingModal(false)}
        activeContext={activeContext}
        backendUrl={BACKEND_URL}
        onOpenContextUpload={() => {
          setShowMeetingModal(false);
          setShowContextModal(true);
        }}
        onViewDebrief={(debriefReport) => {
          setReport(debriefReport);
        }}
      />
    </main>
  );
}

function Logo({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <div className="logo compact">
        <img src="/miles_logo.png" alt="Miles" className="logo-image-compact" />
        <h1>Miles</h1>
      </div>
    );
  }
  return (
    <div className="logo home-logo">
      <img src="/miles_home_logo.png" alt="Miles" className="home-logo-image" />
    </div>
  );
}

export default App;
