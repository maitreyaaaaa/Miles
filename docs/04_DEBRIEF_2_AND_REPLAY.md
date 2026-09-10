# Feature Specification: Final Debrief 2.0 & Interactive Replay Mode

## 1. Problem Statement
1. **Live Interface Distraction**: During real-world negotiations, having live gauges flashing "Cadence 140 WPM" or "Fillers: 3" breaks immersion and increases cognitive load. The live sparring canvas must remain pristine, focused solely on the adversary's voice and subtitles.
2. **Actionable Training Gap**: Standard debriefs offer generic critique. Users want to see:
   - What was their single **weakest answer**?
   - What was their single **strongest answer**?
   - Exactly **what they should have said instead** (executive reframe).
   - The ability to **scrub through and replay the exact moments** where they hesitated or broke.

---

## 2. Debrief 2.0 Architecture

### A. Core Debrief 2.0 Modules

| Section | Description | Source Engine |
| :--- | :--- | :--- |
| **Composure & Cadence Scorecard** | Overall Score (0-100), Composure (0-100), Cadence (WPM), Fillers tally, Barge-ins handled | Normalizer + GPT-4o |
| **Weakest Answer Spotlight** | Highlights the exact answer where the user lost ground, quoting the weakest sentence and explaining why | GPT-4o Transcript Auditor |
| **Strongest Answer Spotlight** | Highlights the answer where the user held firm with concrete evidence and commanding pace | GPT-4o Transcript Auditor |
| **Executive Reframing ("What You Should Have Said")** | Complete rewrites of the 2 most vulnerable answers into crisp, assertive executive answers | GPT-4o Executive Coach |
| **Chronological Moment Replay** | Audio timeline with clickable event markers | Web Audio Buffer Cache |

---

## 3. Interactive Replay Mode

### Timeline Markers
As the debate unfolds, the server logs bookmark timestamps for critical events:
- 🟡 `Hesitation (>2.0s)`: Point where user hesitated before answering.
- 🔴 `AI Cut-in`: Point where Miles interrupted the user for waffling/fillers.
- 🟢 `Barge-in / Recovery`: Point where the user successfully interrupted the AI or asserted a strong counter.
- 💥 `Argument Breakdown`: Point where logical inconsistency was exposed.

### Replay Scrubbing UI
```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 INTERACTIVE MOMENT REPLAY                               │
│  Scrub through key debate turning points to review your performance                      │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [ ▶ Play Session Audio ]   01:42 / 03:15                       Speed: [ 1.0x ▾ ]      │
│                                                                                        │
│  ───●─────────────▲───────────────▲─────────────────────●──────────────▲───────┤       │
│    00:15        00:48           01:12                 02:05          02:45             │
│    Salvo       🟡 Hesitation   🔴 Interrupted        🟢 Barge-in    💥 Break           │
│                                                                                        │
│  [ Selected Moment: 01:12 - AI Interruption ]                                          │
│  Miles cut in: "Cut the buzzwords. What's the actual CAC?"                             │
│  Why: Clustered fillers detected ('um, basically, like').                              │
│  Reframe: "Our CAC is $42 with a 7-month payback window across 1,200 paying seats."    │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```
