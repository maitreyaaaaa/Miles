import React, { useState, useEffect } from "react";
import {
  ArrowRight,
  Play,
  Pause,
  Zap,
  Sparkles,
  CheckCircle2,
  Activity,
  FileText,
  Users,
  Video,
  Gauge,
  Target,
  Radio,
} from "lucide-react";
import type { ScenarioId } from "../types";
import { ShinyText } from "./ShinyText";
import { SpotlightCard } from "./SpotlightCard";
import { BlurText } from "./BlurText";
import { CountUp } from "./CountUp";

interface MarketingLandingProps {
  onStartDebate: (scenarioId?: ScenarioId, customTopic?: string) => void;
  onOpenPreflight: () => void;
  onOpenContextModal: () => void;
  onOpenMeetModal: () => void;
}

const rotatingRoles = [
  "VC pitch",
  "salary talk",
  "hard question",
  "board meeting",
  "press mess",
];

export const MarketingLanding: React.FC<MarketingLandingProps> = ({
  onStartDebate,
  onOpenPreflight,
  onOpenContextModal,
  onOpenMeetModal,
}) => {
  const [roleIndex, setRoleIndex] = useState(0);
  const [customTopic, setCustomTopic] = useState("");
  const [selectedHeroScenario, setSelectedHeroScenario] = useState<ScenarioId>("vc_pitch");
  const [playingSample, setPlayingSample] = useState<string | null>(null);

  useEffect(() => {
    const interval = setInterval(() => {
      setRoleIndex((prev) => (prev + 1) % rotatingRoles.length);
    }, 2800);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const revealItems = Array.from(document.querySelectorAll<HTMLElement>(".reveal-on-scroll"));
    if (motionQuery.matches || !("IntersectionObserver" in window)) {
      revealItems.forEach((item) => item.classList.add("is-visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.16 },
    );

    revealItems.forEach((item) => observer.observe(item));
    return () => observer.disconnect();
  }, []);

  const handleCustomTopicSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (customTopic.trim()) {
      onStartDebate("custom_debate", customTopic.trim());
    } else {
      onStartDebate("custom_debate");
    }
  };

  const toggleSample = (id: string) => {
    if (playingSample === id) {
      setPlayingSample(null);
    } else {
      setPlayingSample(id);
      // Auto-stop simulation after 4 seconds
      setTimeout(() => {
        setPlayingSample((current) => (current === id ? null : current));
      }, 4200);
    }
  };

  return (
    <div className="marketing-shell">
      {/* =========================================================================
          HERO VIEWPORT (With Iconic Lime Artwork Background)
          ========================================================================= */}
      <section className="hero-viewport">
        <div className="hero-texture-layer" aria-hidden="true" />
        <div className="hero-ambient-lines" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>

        {/* TOP CORNER EDITORIAL BADGES */}
        <div className="hero-top-corners">
          <div className="hero-corner-item hero-corner-tl">
            <ShinyText text="STOP WINGING IT" speed={5} />
            <span>LOCK IN FIRST</span>
          </div>
          <div className="hero-corner-item hero-corner-tr">
            <span>PRACTICE OUT LOUD</span>
            <div className="hero-corner-dash" />
            <span>BEFORE IT COUNTS</span>
          </div>
        </div>

        {/* SIDE TYPOGRAPHIC ANNOTATIONS */}
        <aside className="hero-side-annotation hero-annotation-left" aria-hidden="true">
          <div className="annotation-content">
            <span>SPEAK</span>
            <span>THINK</span>
            <span>LOCK IN</span>
            <span>REPEAT.</span>
          </div>
        </aside>
        <aside className="hero-side-annotation hero-annotation-right" aria-hidden="true">
          <div className="annotation-content">
            <span>IDEAS</span>
            <span>PRESSURE</span>
            <span>ANSWERS</span>
            <span>NO PANIC</span>
            <svg className="hero-curved-arrow-svg" viewBox="0 0 54 54" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 44C16 26 26 14 44 10M44 10L32 8M44 10L40 22" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </aside>

        {/* BOTTOM RIGHT CORNER BADGE */}
        <div className="hero-corner-item hero-corner-br" aria-hidden="true">
          <span>REAL TALK</span>
          <span>NO SAFE MODE</span>
          <div className="hero-corner-dash" />
        </div>

        {/* HERO CONTENT CONTAINER */}
        <div className="hero-content-wrapper">
          {/* LOGO */}
          <div className="hero-logo-box">
            <img
              src="/miles_home_logo.png"
              alt="Miles Logo"
              className="hero-logo-img"
            />
          </div>

          {/* DYNAMIC ROTATING HOOK BADGE */}
          <div className="hero-dynamic-pill">
            <span className="hero-pill-prefix">Do not get cooked in a</span>
            <span className="hero-rotating-word" key={roleIndex}>
              {rotatingRoles[roleIndex]}
            </span>
          </div>

          {/* HEADLINE */}
          <h1 className="hero-headline">
            <BlurText text="Practice the" delay={45} />{" "}
            <span className="headline-cursive">conversation</span>{" "}
            <BlurText text="before it gets real." delay={45} />
          </h1>

          {/* SUBTITLE */}
          <p className="hero-subtitle">
            Miles talks with you out loud, pushes back, cuts in when you dodge,
            and shows where you lost the plot. It is practice for hard rooms.
          </p>

          {/* PRIMARY CALL TO ACTION BUTTON */}
          <div style={{ display: "flex", justifyContent: "center" }}>
            <button
                type="button"
                className="hero-start-cta"
                onClick={() => onStartDebate(selectedHeroScenario)}
              >
                Start a round
              </button>
          </div>

          {/* CUSTOM TOPIC CAPSULE */}
          <div className="hero-topic-maker">
            <label htmlFor="hero-custom-topic-input" className="hero-topic-label">
              Make your own topic. Be so for real.
            </label>
            <form className="hero-topic-capsule" onSubmit={handleCustomTopicSubmit}>
              <input
                id="hero-custom-topic-input"
                type="text"
                placeholder="e.g. Remote work makes teams worse"
                value={customTopic}
                onChange={(e) => setCustomTopic(e.target.value)}
              />
              <button
                type="submit"
                className="hero-topic-arrow-btn"
                title="Practice this topic"
              >
                <ArrowRight size={16} />
              </button>
            </form>
          </div>

          {/* 3 FEATURED SCENARIO CARDS */}
          <div className="hero-featured-grid">
            <button
              type="button"
              className={`hero-scenario-card ${selectedHeroScenario === "vc_pitch" ? "selected" : ""}`}
              onClick={() => {
                setSelectedHeroScenario("vc_pitch");
                onStartDebate("vc_pitch");
              }}
            >
              <span className="hero-card-tag">STARTUPS</span>
              <strong className="hero-card-title">Pitch without folding</strong>
              <p className="hero-card-desc">
                Explain your idea, your numbers, and why anyone should care.
              </p>
            </button>

            <button
              type="button"
              className={`hero-scenario-card ${selectedHeroScenario === "salary_negotiation" ? "selected" : ""}`}
              onClick={() => {
                setSelectedHeroScenario("salary_negotiation");
                onStartDebate("salary_negotiation");
              }}
            >
              <span className="hero-card-tag">CAREER</span>
              <strong className="hero-card-title">Ask for more money</strong>
              <p className="hero-card-desc">
                Say your number clearly and stop apologizing for wanting it.
              </p>
            </button>

            <button
              type="button"
              className={`hero-scenario-card ${selectedHeroScenario === "hostile_cross_exam" ? "selected" : ""}`}
              onClick={() => {
                setSelectedHeroScenario("hostile_cross_exam");
                onStartDebate("hostile_cross_exam");
              }}
            >
              <span className="hero-card-tag">LEGAL</span>
              <strong className="hero-card-title">Do not crumble</strong>
              <p className="hero-card-desc">
                Handle sharp questions without rambling yourself into a hole.
              </p>
            </button>
          </div>
        </div>

        {/* MULTI-STOP SMOOTH GRADIENT FADE */}
        <div className="hero-gradient-fade" />
      </section>

      <section className="product-proof-strip reveal-on-scroll" aria-label="Product evidence">
        <div className="proof-strip-inner">
          <div className="proof-copy">
            <span className="proof-kicker">For the moment before the room goes quiet</span>
            <strong>Practice out loud. Get interrupted. Learn what to fix.</strong>
          </div>
          <div className="proof-metrics">
            <div>
              <Activity size={16} />
              <span>See your pace</span>
            </div>
            <div>
              <Radio size={16} />
              <span>Talk both ways</span>
            </div>
            <div>
              <FileText size={16} />
              <span>Use your deck</span>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION / 01 — THE REALITY (The Problem & Contrast)
          ========================================================================= */}
      <section className="marketing-section section-dark reveal-on-scroll" id="the-reality">
        <div className="section-container">
          <div className="section-index-badge">
            <span className="badge-dot" />
            <span>/ 01 — THE PROBLEM</span>
          </div>

          <h2 className="section-headline">
            Most people practice the big conversation in their head and call it prep.
          </h2>
          <p className="section-lead">
            Then the real person asks one hard question and suddenly the brain tabs are all crashing.
            Miles lets you feel that pressure before it matters.
          </p>

          <div className="contrast-grid">
            <div className="contrast-card contrast-standard reveal-on-scroll">
              <div className="contrast-card-header">
                <span className="contrast-pill standard-pill">Normal AI chat</span>
                <span className="contrast-status">Too polite</span>
              </div>
              <ul className="contrast-list">
                <li>
                  <strong>It keeps glazing you:</strong> "Great point" this, "nice idea" that. Bestie, that is not practice.
                </li>
                <li>
                  <strong>It lets you ramble:</strong> You can yap for two minutes and nothing bad happens.
                </li>
                <li>
                  <strong>No pressure:</strong> You feel safe, then the real meeting humbles you instantly.
                </li>
                <li>
                  <strong>It cannot hear you:</strong> It misses your pauses, filler words, and panic speed.
                </li>
              </ul>
            </div>

            <div className="contrast-card contrast-miles reveal-on-scroll">
              <div className="contrast-card-header">
                <span className="contrast-pill miles-pill">Miles</span>
                <span className="contrast-status status-active">Locked in</span>
              </div>
              <ul className="contrast-list">
                <li>
                  <strong>No fake hype:</strong> Miles pushes back when your answer is weak.
                </li>
                <li>
                  <strong>It cuts in:</strong> If you dodge, stall, or waffle, Miles calls it out.
                </li>
                <li>
                  <strong>It tracks the basics:</strong> Pace, filler words, and how calm you sound.
                </li>
                <li>
                  <strong>It uses your own stuff:</strong> Add a deck and Miles asks about the weak parts.
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION / 02 — ADVERSARIAL CAPABILITIES (Interactive Bento Grid)
          ========================================================================= */}
      <section className="marketing-section section-dark-bento reveal-on-scroll" id="capabilities">
        <div className="section-container">
          <div className="section-index-badge">
            <span className="badge-dot" />
            <span>/ 02 — WHAT IT DOES</span>
          </div>

          <h2 className="section-headline">
            It is basically a gym for hard conversations.
          </h2>
          <p className="section-lead">
            You pick the room. Miles plays the hard person in that room.
            You talk. It pushes back. Then you see what needs work.
          </p>

          <div className="bento-grid">
            {/* CARD 1: Barge-in & Interruption */}
            <SpotlightCard className="bento-card bento-card-large reveal-on-scroll" spotlightColor="rgba(198, 244, 50, 0.12)">
              <div className="bento-card-icon-box">
                <Zap size={22} className="bento-icon" />
                <span className="bento-tech-tag">Fast voice mode</span>
              </div>
              <div className="signal-radar" aria-hidden="true">
                <span className="radar-core" />
                <span className="radar-ring ring-one" />
                <span className="radar-ring ring-two" />
                <span className="radar-pulse" />
              </div>
              <h3 className="bento-card-title">It interrupts you fast</h3>
              <p className="bento-card-desc">
                Real people do not always wait their turn. Miles can cut in when you stall,
                and it can stop talking when you jump in. Very rude, very useful.
              </p>
              <div className="bento-latency-meter">
                <div className="meter-label">
                  <span>Cut-in speed</span>
                  <span className="meter-val">very fast</span>
                </div>
                <div className="meter-bar-track">
                  <div className="meter-bar-fill" style={{ width: "24%" }} />
                </div>
              </div>
            </SpotlightCard>

            {/* CARD 2: Composure & Cadence HUD */}
            <SpotlightCard className="bento-card reveal-on-scroll" spotlightColor="rgba(198, 244, 50, 0.12)">
              <div className="bento-card-icon-box">
                <Gauge size={22} className="bento-icon" />
                <span className="bento-tech-tag">Calm check</span>
              </div>
              <h3 className="bento-card-title">It notices when you sound shaky</h3>
              <p className="bento-card-desc">
                Miles listens for speed, long pauses, and filler words like "um," "uh," "like,"
                and "basically." No shame. Just data.
              </p>
              <div className="bento-hud-preview">
                <div className="hud-pill">
                  <span className="hud-metric"><CountUp to={100} duration={1.2} /></span>
                  <span className="hud-lbl">Calm</span>
                </div>
                <div className="hud-pill">
                  <span className="hud-metric"><CountUp to={142} duration={1.2} /></span>
                  <span className="hud-lbl">Words per min</span>
                </div>
                <div className="hud-pill">
                  <span className="hud-metric"><CountUp to={0} duration={1.2} /></span>
                  <span className="hud-lbl">Filler words</span>
                </div>
              </div>
              <div className="composure-wave" aria-hidden="true">
                <span />
                <span />
                <span />
                <span />
                <span />
                <span />
              </div>
            </SpotlightCard>

            {/* CARD 3: Anti-Sycophancy Policy */}
            <SpotlightCard className="bento-card reveal-on-scroll" spotlightColor="rgba(198, 244, 50, 0.12)">
              <div className="bento-card-icon-box">
                <Target size={22} className="bento-icon" />
                <span className="bento-tech-tag">No glazing</span>
              </div>
              <h3 className="bento-card-title">It will not pretend your answer ate</h3>
              <p className="bento-card-desc">
                If your point is weak, Miles says so. Not to be mean.
                To help you fix it before someone important says it worse.
              </p>
              <div className="policy-stack" aria-hidden="true">
                <span>ask why</span>
                <span>ask for proof</span>
                <span>stop the dodge</span>
              </div>
            </SpotlightCard>

            {/* CARD 4: Document Weaponization */}
            <SpotlightCard className="bento-card reveal-on-scroll" spotlightColor="rgba(198, 244, 50, 0.12)">
              <div className="bento-card-icon-box">
                <FileText size={22} className="bento-icon" />
                <span className="bento-tech-tag">Bring receipts</span>
              </div>
              <h3 className="bento-card-title">Upload your deck and get cooked safely</h3>
              <p className="bento-card-desc">
                Add a pitch deck, contract, or notes. Miles uses your own words and numbers
                to ask better questions. Painful, but useful.
              </p>
              <div className="doc-scan" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
            </SpotlightCard>

            {/* CARD 5: Multi-Agent Boardroom Panel */}
            <SpotlightCard className="bento-card reveal-on-scroll" spotlightColor="rgba(198, 244, 50, 0.12)">
              <div className="bento-card-icon-box">
                <Users size={22} className="bento-icon" />
                <span className="bento-tech-tag">Two-on-one</span>
              </div>
              <h3 className="bento-card-title">Two people can pressure you at once</h3>
              <p className="bento-card-desc">
                One sounds helpful. One is not buying it at all.
                You learn how to stay clear when the room gets weird.
              </p>
              <div className="panel-orbit" aria-hidden="true">
                <span>VC</span>
                <span>GC</span>
                <span>YOU</span>
              </div>
            </SpotlightCard>

            {/* CARD 6: Executive Debrief PDF */}
            <SpotlightCard className="bento-card reveal-on-scroll" spotlightColor="rgba(198, 244, 50, 0.12)">
              <div className="bento-card-icon-box">
                <Sparkles size={22} className="bento-icon" />
                <span className="bento-tech-tag">After-round notes</span>
              </div>
              <h3 className="bento-card-title">You get a simple debrief after</h3>
              <p className="bento-card-desc">
                See where you got vague, where you rushed, and what to say better next time.
                No mystery. Just the fix list.
              </p>
              <div className="debrief-preview" aria-hidden="true">
                <CheckCircle2 size={15} />
                <span>3 practice drills ready</span>
              </div>
            </SpotlightCard>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION / 03 — HOW IT WORKS (4-Step Numerical Sequence)
          ========================================================================= */}
      <section className="marketing-section section-dark reveal-on-scroll" id="how-it-works">
        <div className="section-container">
          <div className="section-index-badge">
            <span className="badge-dot" />
            <span>/ 03 — HOW IT WORKS</span>
          </div>

          <h2 className="section-headline">
            Four steps. No 40-minute setup arc.
          </h2>
          <p className="section-lead">
            This is not another chat box. You talk out loud, get challenged,
            and leave with a clearer answer.
          </p>

          <div className="steps-sequence-grid">
            <div className="step-card reveal-on-scroll">
              <div className="step-num">01</div>
              <div className="step-header">Pick the room</div>
              <p className="step-desc">
                Choose a pitch, salary talk, interview, board meeting, legal question,
                or write your own spicy topic.
              </p>
            </div>

            <div className="step-card reveal-on-scroll">
              <div className="step-num">02</div>
              <div className="step-header">Choose the heat</div>
              <p className="step-desc">
                Keep it chill or make it brutal. Add a deck if you want Miles to use your real material.
              </p>
            </div>

            <div className="step-card reveal-on-scroll">
              <div className="step-num">03</div>
              <div className="step-header">Talk under pressure</div>
              <p className="step-desc">
                Use your mic. Answer like it is the real meeting.
                Miles pushes back when your answer gets soft.
              </p>
            </div>

            <div className="step-card reveal-on-scroll">
              <div className="step-num">04</div>
              <div className="step-header">Read the fix list</div>
              <p className="step-desc">
                See what went well, what got messy, and what to practice next.
                That is the whole point.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION / 04 — AUDIO SIMULATION TEASER (Interactive Soundboard)
          ========================================================================= */}
      <section className="marketing-section section-dark-bento reveal-on-scroll" id="audio-simulation">
        <div className="section-container">
          <div className="section-index-badge">
            <span className="badge-dot" />
            <span>/ 04 — TRY THE VIBE</span>
          </div>

          <h2 className="section-headline">
            Hear the kind of questions{" "}
            <span className="heading-logo-word">
              <img src="/miles_wordmark.png" alt="Miles" />
            </span>{" "}
            throws at you.
          </h2>
          <p className="section-lead">
            These are sample prompts, not actual audio recordings. Click one and the card comes alive.
          </p>

          <div className="audio-samples-grid">
            {/* Sample 1: Marcus Vance (VC) */}
            <div className={`audio-sample-card reveal-on-scroll ${playingSample === "marcus" ? "is-playing" : ""}`}>
              <div className="sample-card-top">
                <div className="sample-avatar-box">
                  <span className="sample-avatar-label">MV</span>
                </div>
                <div className="sample-meta">
                  <span className="sample-name">Marcus Vance</span>
                  <span className="sample-role">Investor who needs real answers</span>
                </div>
                <button
                  type="button"
                  className="sample-play-btn"
                  onClick={() => toggleSample("marcus")}
                  title={playingSample === "marcus" ? "Pause challenge" : "Listen to challenge"}
                >
                  {playingSample === "marcus" ? <Pause size={16} /> : <Play size={16} />}
                </button>
              </div>

              <div className="sample-quote">
                "Your growth looks expensive. Why would this not get copied by a bigger team with more money?"
              </div>

              <div className="sample-audio-bars">
                <span className={`bar ${playingSample === "marcus" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "marcus" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "marcus" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "marcus" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "marcus" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "marcus" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "marcus" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "marcus" ? "active" : ""}`} />
              </div>
            </div>

            {/* Sample 2: Elena Rostova (Salary) */}
            <div className={`audio-sample-card reveal-on-scroll ${playingSample === "elena" ? "is-playing" : ""}`}>
              <div className="sample-card-top">
                <div className="sample-avatar-box">
                  <span className="sample-avatar-label">ER</span>
                </div>
                <div className="sample-meta">
                  <span className="sample-name">Elena Rostova</span>
                  <span className="sample-role">Hiring lead who will not overpay for vibes</span>
                </div>
                <button
                  type="button"
                  className="sample-play-btn"
                  onClick={() => toggleSample("elena")}
                  title={playingSample === "elena" ? "Pause challenge" : "Listen to challenge"}
                >
                  {playingSample === "elena" ? <Pause size={16} /> : <Play size={16} />}
                </button>
              </div>

              <div className="sample-quote">
                "That salary ask is high. What did you actually do that makes this number make sense?"
              </div>

              <div className="sample-audio-bars">
                <span className={`bar ${playingSample === "elena" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "elena" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "elena" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "elena" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "elena" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "elena" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "elena" ? "active" : ""}`} />
                <span className={`bar ${playingSample === "elena" ? "active" : ""}`} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          SECTION / 05 — READY TO SPAR CTA (High-Impact Action Box)
          ========================================================================= */}
      <section className="marketing-section section-cta reveal-on-scroll">
        <div className="section-container cta-container">
          <div className="cta-glow-spot" />
          <div className="cta-content-box">
            <span className="cta-eyebrow">
              <ShinyText text="READY TO STOP GUESSING?" speed={4} />
            </span>
            <h2 className="cta-title">
              Stop rehearsing in the mirror.<br />
              Let{" "}
              <span className="heading-logo-word cta-logo-word">
                <img src="/miles_wordmark.png" alt="Miles" />
              </span>{" "}
              press you a little.
            </h2>
            <p className="cta-subtitle">
              Put on headphones, pick a room, and say the answer out loud.
              You will know very quickly what needs work.
            </p>

            <div className="cta-action-row">
              <button
                  type="button"
                  className="cta-primary-btn"
                  onClick={() => onStartDebate()}
                >
                  <span>Start a round</span>
                  <span className="cta-icon-island">
                    <ArrowRight size={16} />
                  </span>
                </button>

              <button
                type="button"
                className="cta-secondary-btn"
                onClick={onOpenMeetModal}
              >
                <Video size={16} />
                <span>Practice in Meet</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          MODERN MARKETING FOOTER
          ========================================================================= */}
      <footer className="marketing-footer">
        <div className="footer-container">
          <div className="footer-top-row">
            <div className="footer-brand-box">
              <img
                src="/miles_home_logo.png"
                alt="Miles"
                className="footer-brand-logo"
              />
              <p className="footer-brand-tagline">
                Miles helps you practice hard conversations out loud before they happen for real.
              </p>
            </div>

            <div className="footer-links-group">
              <div className="footer-col">
                <span className="footer-col-header">SCENARIOS</span>
                <button type="button" onClick={() => onStartDebate("vc_pitch")}>Pitch practice</button>
                <button type="button" onClick={() => onStartDebate("salary_negotiation")}>Salary talk</button>
                <button type="button" onClick={() => onStartDebate("hostile_cross_exam")}>Hard questions</button>
                <button type="button" onClick={() => onStartDebate("senior_interview")}>Job interview</button>
              </div>

              <div className="footer-col">
                <span className="footer-col-header">EXPLORE</span>
                <a href="#how-it-works">How it works</a>
                <a href="#capabilities">What Miles does</a>
                <a href="#audio-simulation">Sample questions</a>
                <button type="button" onClick={onOpenPreflight}>Check audio</button>
              </div>

              <div className="footer-col">
                <span className="footer-col-header">INTEGRATIONS</span>
                <button type="button" onClick={onOpenMeetModal}>Google Meet mode</button>
                <button type="button" onClick={onOpenContextModal}>Attach a deck</button>
                <button type="button" onClick={() => onStartDebate("custom_debate")}>Custom topic</button>
              </div>
            </div>
          </div>

          <div className="footer-bottom-row">
            <div className="footer-tech-stack">
              <span>BUILT WITH:</span>
              <span className="tech-badge">Live speech</span>
              <span className="tech-badge">Voice replies</span>
              <span className="tech-badge">Fast web audio</span>
            </div>

            <div className="footer-copyright">
              © {new Date().getFullYear()} Miles Voice AI. Practice the hard conversation before it practices on you.
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};
