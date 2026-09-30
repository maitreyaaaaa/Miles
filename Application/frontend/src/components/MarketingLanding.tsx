import { useEffect, useState } from "react";
import { Activity, ArrowRight, CheckCircle2, FileText, Gauge, Mic, ShieldCheck, Target, Video, Zap } from "lucide-react";
import type { ScenarioId } from "../types";
import { GOOGLE_MEET_ENABLED } from "../features";
import { scenarios } from "../scenarios";

interface MarketingLandingProps {
  onStartDebate: (scenarioId?: ScenarioId, customTopic?: string) => void;
  onOpenPreflight: () => void;
  onOpenContextModal: () => void;
  onOpenMeetModal: () => void;
}

const examples: Record<ScenarioId, { question: string; answer: string; feedback: string }> = {
  vc_pitch: { question: "What stops a bigger company from copying this?", answer: "Our advantage is the workflow and distribution we have built with customers.", feedback: "Lead with the advantage, then support it with evidence." },
  salary_negotiation: { question: "What results support the salary you are asking for?", answer: "I led the launch, improved retention, and can show the impact against our targets.", feedback: "Connect your request to specific outcomes." },
  hostile_cross_exam: { question: "What did you personally observe, and what are you assuming?", answer: "I can speak to what I saw. I cannot confirm what happened before I arrived.", feedback: "Separate facts from assumptions and keep the answer direct." },
  senior_interview: { question: "Why did you choose this architecture over the simpler option?", answer: "The simpler option works today. This design addresses our consistency requirements as traffic grows.", feedback: "State the requirement and explain the tradeoff." },
  sales_objections: { question: "Why should we switch when our current tool already works?", answer: "The difference is the time your team spends on exceptions. Let us measure that in a pilot.", feedback: "Answer the objection with a measurable customer outcome." },
  media_crisis: { question: "What do you know now, and what are you doing about it?", answer: "We have confirmed the incident, contained access, and will share verified updates as the investigation progresses.", feedback: "Be precise about confirmed facts and next actions." },
  hostile_boardroom: { question: "Why should we back this plan if margins are falling?", answer: "The plan addresses the two largest cost drivers. I can walk through the assumptions and milestones.", feedback: "Own the issue and show how you will measure progress." },
  custom_debate: { question: "What evidence would make you change your position?", answer: "A result that contradicts my core assumption would change it. Here is how I would test that.", feedback: "Name the assumption and make the claim testable." },
};

export function MarketingLanding({ onStartDebate, onOpenPreflight, onOpenContextModal, onOpenMeetModal }: MarketingLandingProps) {
  const [customTopic, setCustomTopic] = useState("");
  const [previewScenario, setPreviewScenario] = useState<ScenarioId>("vc_pitch");
  const example = examples[previewScenario];

  useEffect(() => {
    const items = Array.from(document.querySelectorAll<HTMLElement>(".marketing-shell .reveal-on-scroll"));
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (motion.matches || !("IntersectionObserver" in window)) {
      items.forEach((item) => item.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const element = entry.target as HTMLElement;
        element.dataset.inView = String(entry.isIntersecting);
        if (entry.isIntersecting) element.classList.add("is-visible");
      });
    }, { rootMargin: "0px 0px -5% 0px", threshold: 0.08 });
    items.forEach((item) => observer.observe(item));
    return () => observer.disconnect();
  }, []);

  const chooseScenario = () => document.getElementById("practice-scenarios")?.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
  });

  return (
    <div className="marketing-shell">
      <section className="hero-viewport">
        <div className="hero-top-corners">
          <div className="hero-corner-item hero-corner-tl"><span>PRACTICE OUT LOUD</span><span>BEFORE IT MATTERS</span></div>
          <div className="hero-corner-item hero-corner-tr"><span>YOUR AI SPARRING PARTNER</span></div>
        </div>
        <div className="hero-content-wrapper">
          <div className="hero-logo-box"><img src="/miles_home_logo.png" alt="Miles" className="hero-logo-img" /></div>
          <div className="hero-dynamic-pill"><Mic size={14} /><span>Real voice practice. Useful feedback.</span></div>
          <h1 className="hero-headline">Practice difficult <span className="headline-cursive">conversations</span> before they matter.</h1>
          <p className="hero-subtitle">Miles is your AI voice sparring partner for pitches, interviews, negotiations, and tough questions. Practice out loud, handle realistic pushback, and leave with a report showing what to improve.</p>
          <div className="hero-actions">
            <button type="button" className="hero-start-cta" onClick={chooseScenario}>Start practicing <ArrowRight size={17} /></button>
            <a className="hero-preview-link" href="#sample-report">See a sample report</a>
          </div>
          <p className="hero-practice-note">Practice in your browser with a microphone and headphones.</p>
          <div className="hero-topic-maker">
            <label htmlFor="hero-custom-topic-input" className="hero-topic-label">Have a specific conversation in mind?</label>
            <form className="hero-topic-capsule" onSubmit={(event) => {
              event.preventDefault();
              if (customTopic.trim()) onStartDebate("custom_debate", customTopic.trim());
            }}>
              <input id="hero-custom-topic-input" type="text" value={customTopic} maxLength={2000}
                onChange={(event) => setCustomTopic(event.target.value)} placeholder="e.g. Defend our pricing strategy" required />
              <button type="submit" className="hero-topic-arrow-btn" aria-label="Practice your custom topic"><ArrowRight size={16} /></button>
            </form>
          </div>
        </div>
      </section>

      <section className="product-proof-strip reveal-on-scroll" aria-label="What you get">
        <div className="proof-strip-inner">
          <div className="proof-copy"><span className="proof-kicker">Prepare for the conversation ahead</span><strong>Speak. Get challenged. Know what to improve.</strong></div>
          <div className="proof-metrics">
            <div><Mic size={16} /><span>Live voice practice</span></div>
            <div><FileText size={16} /><span>Your documents as context</span></div>
            <div><Activity size={16} /><span>A report after every round</span></div>
          </div>
        </div>
      </section>

      <section className="marketing-section section-dark reveal-on-scroll" id="practice-scenarios">
        <div className="section-container">
          <div className="section-index-badge"><span className="badge-dot" /><span>CHOOSE YOUR CONVERSATION</span></div>
          <h2 className="section-headline">A practice room for every difficult conversation.</h2>
          <p className="section-lead">Pick what you are preparing for. Adjust the pressure before you start.</p>
          <div className="practice-scenario-grid">
            {scenarios.map((scenario) => (
              <button type="button" className="practice-scenario-card" key={scenario.id} onClick={() => onStartDebate(scenario.id)}>
                <span className="practice-scenario-tag">{scenario.tag}</span>
                <h3>{scenario.label}</h3>
                <p>{scenario.topic}</p>
                <span className="practice-scenario-action">Practice this scenario <ArrowRight size={15} /></span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="marketing-section section-dark-bento reveal-on-scroll" id="capabilities">
        <div className="section-container">
          <div className="section-index-badge"><span className="badge-dot" /><span>WHAT MILES HELPS YOU DO</span></div>
          <h2 className="section-headline">Turn a rehearsed answer into a clear conversation.</h2>
          <div className="practice-benefits">
            {[
              { icon: Zap, title: "Handle real pushback", text: "Miles questions your assumptions, asks for evidence, and follows up when an answer is vague. You can interrupt and respond naturally." },
              { icon: Gauge, title: "Understand your delivery", text: "Review your pace, filler words, and moments of hesitation alongside feedback on your answers." },
              { icon: FileText, title: "Practice with your own material", text: "Add a pitch deck as PDF, a document, or notes. Miles uses your context to challenge your claims and numbers." },
              { icon: Target, title: "Leave with a next step", text: "See strengths, weak answers, and suggested improvements in your report. Retry an answer and download your feedback as PDF." },
            ].map(({ icon: Icon, title, text }) => (
              <article className="practice-benefit" key={title}><Icon size={23} /><h3>{title}</h3><p>{text}</p></article>
            ))}
          </div>
        </div>
      </section>

      <section className="marketing-section section-dark reveal-on-scroll" id="how-it-works">
        <div className="section-container">
          <div className="section-index-badge"><span className="badge-dot" /><span>HOW IT WORKS</span></div>
          <h2 className="section-headline">From preparation to a useful report.</h2>
          <div className="steps-sequence-grid">
            {[
              ["Choose a scenario", "Pick a pitch, negotiation, interview, or another challenge. Set a difficulty that fits your practice."],
              ["Add context if you want", "Upload a supported document or paste notes. Check your microphone, headphones, and voice connection."],
              ["Practice out loud", "Miles plays the other side. Answer questions, handle objections, and keep the conversation clear."],
              ["Get your feedback", "Finish the round to see what worked, what needs practice, and how to improve. Download your report."],
            ].map(([title, text], index) => <article className="step-card" key={title}>
              <div className="step-num">0{index + 1}</div><h3 className="step-header">{title}</h3><p className="step-desc">{text}</p>
            </article>)}
          </div>
        </div>
      </section>

      <section className="marketing-section section-dark-bento reveal-on-scroll" id="audio-simulation">
        <div className="section-container">
          <div className="section-index-badge"><span className="badge-dot" /><span>A LOOK INSIDE A ROUND</span></div>
          <h2 className="section-headline">Practice the follow-up question, too.</h2>
          <p className="section-lead">Illustrative examples below. Your live conversation responds to what you actually say.</p>
          <div className="preview-scenario-tabs" aria-label="Example conversations">
            {scenarios.map((scenario) => <button type="button" key={scenario.id}
              aria-pressed={previewScenario === scenario.id} onClick={() => setPreviewScenario(scenario.id)}>{scenario.label}</button>)}
          </div>
          <div className="conversation-preview reveal-on-scroll" aria-live="polite">
            <div className="preview-conversation-label"><span>EXAMPLE CONVERSATION</span>
              <div className="preview-wave" aria-hidden="true">{[0, 1, 2, 3, 4].map((index) => <span key={index} />)}</div>
            </div>
            <div className="preview-message"><strong>Miles</strong><p>{example.question}</p></div>
            <div className="preview-message preview-message-user"><strong>You</strong><p>{example.answer}</p></div>
            <div className="preview-feedback"><CheckCircle2 size={18} /><p>{example.feedback}</p></div>
          </div>
        </div>
      </section>

      <section className="marketing-section section-dark reveal-on-scroll" id="sample-report">
        <div className="section-container">
          <div className="section-index-badge"><span className="badge-dot" /><span>AFTER YOUR ROUND</span></div>
          <h2 className="section-headline">Know what to keep. Know what to change.</h2>
          <p className="section-lead">Your report connects feedback to your spoken answers. Speech metrics come from the captured session; argument scores are AI assessments.</p>
          <div className="sample-report-card">
            <div className="sample-report-header"><FileText size={23} /><div><h3>Your practice report</h3><span>Illustrative preview · values below are examples</span></div></div>
            <div className="sample-report-metrics">
              <div><strong>142</strong><span>Words per minute</span></div><div><strong>4</strong><span>Filler words</span></div><div><strong>3</strong><span>Spoken answers</span></div>
            </div>
            <div className="sample-report-columns">
              <div><h4>What worked</h4><p>You answered the question before explaining the background.</p></div>
              <div><h4>What to improve</h4><p>Your claim about customer demand needs a specific example or number.</p></div>
              <div><h4>Try next time</h4><p>Lead with your answer, give one piece of evidence, and stop there.</p></div>
            </div>
            <p className="sample-report-note"><ShieldCheck size={16} /> In-app feedback, PDF download, and a share link you choose to create.</p>
          </div>
        </div>
      </section>

      <section className="marketing-section section-cta reveal-on-scroll">
        <div className="section-container cta-container">
          <div className="cta-content-box">
            <h2 className="cta-title">Have the practice conversation first.</h2>
            <p className="cta-subtitle">Pick your scenario, put on headphones, and give your answer out loud.</p>
            <div className="cta-action-row">
              <button type="button" className="cta-primary-btn" onClick={chooseScenario}><span>Start practicing</span><ArrowRight size={17} /></button>
              {GOOGLE_MEET_ENABLED && <button type="button" className="cta-secondary-btn" onClick={onOpenMeetModal}><Video size={16} /><span>Practice in Meet</span></button>}
            </div>
          </div>
        </div>
      </section>

      <footer className="marketing-footer">
        <div className="footer-container">
          <div className="footer-top-row">
            <div className="footer-brand-box"><img src="/miles_home_logo.png" alt="Miles" className="footer-brand-logo" /><p className="footer-brand-tagline">An AI voice sparring partner for the conversations that matter.</p></div>
            <div className="footer-links-group">
              <div className="footer-col"><span className="footer-col-header">PRACTICE</span><a href="#practice-scenarios">All scenarios</a><button type="button" onClick={onOpenPreflight}>Check audio</button><button type="button" onClick={onOpenContextModal}>Add a PDF or notes</button></div>
              <div className="footer-col"><span className="footer-col-header">EXPLORE</span><a href="#how-it-works">How it works</a><a href="#audio-simulation">Example conversations</a><a href="#sample-report">Sample report</a>{GOOGLE_MEET_ENABLED && <button type="button" onClick={onOpenMeetModal}>Google Meet mode</button>}</div>
            </div>
          </div>
          <div className="footer-bottom-row"><div className="footer-tech-stack"><span>Speech recognition powered by AssemblyAI</span></div><div className="footer-copyright">Miles · Practice before it matters.</div></div>
        </div>
      </footer>
    </div>
  );
}
