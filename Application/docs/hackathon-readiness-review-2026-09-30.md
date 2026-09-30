# Miles hackathon readiness review

Reviewed 30 September 2026. Repository: `D:\Voice AI`; application: `D:\Voice AI\Application`.

Scope: inspect the current product and propose options before implementation. No application behavior or deployment settings changed. The user wants Google Meet hidden without deleting its implementation, all sparring scenarios presented equally, clear landing-page messaging, modest animation, reliable built-in voice practice, and a useful report.

## Recommendation and Meet options

| Option | Behavior | Tradeoff |
| --- | --- | --- |
| Hide UI entry points | Conditionally render Meet navigation, CTA, footer, and dialogs. | Smallest change, but direct API calls and the audio bridge remain available. |
| Feature switches across UI and backend — recommended | Hide Meet UI and prevent new meeting provisioning, scheduling, bot launches, and bridge connections. Keep the implementation, records, and tests. | Slightly more work; reversible and consistent with a sparring-only production release. |
| Sparring-only build | Exclude meeting components and the bridge HTML from the production build, alongside backend gating. | Smaller deployment surface, but introduces more build-specific behavior to maintain under a deadline. |

Proposed configuration: backend `GOOGLE_MEET_ENABLED=false` and frontend `VITE_GOOGLE_MEET_ENABLED=false`, documented in both environment examples. These names are proposals, not existing settings. Backend enforcement is authoritative; Vite settings require a frontend rebuild. A safe capability response can also keep the UI aligned with backend availability.

Cover all Meet surfaces: `MarketingLanding.tsx` has a "Practice in Meet" CTA and "Google Meet mode" footer link. `App.tsx` has arena navigation and mounts the meeting scheduler in three views. `server.py` exposes provisioning, scheduling, launch, status, report, webhook, and bridge paths. `vite.config.ts` currently builds `meeting-bridge.html` as a separate entry point.

Disable creation and entry before any provider call. Gate Calendar consent associated with meeting creation, while retaining Google sign-in and separate Google Drive document imports. Do not use CSS hiding as enforcement. Preserve lifecycle webhooks and owner-scoped stop/cancel operations where necessary to clean up existing bots; inspect active/scheduled bots before rollout. Never delete meeting records or cancel external bots automatically as part of this review.

## Current strengths and concrete gaps

- **Core product exists:** eight frontend choices cover VC pitch, salary negotiation, cross-examination, systems architecture, enterprise sales, media crisis, boardroom, and custom debate. Backend personas, interruption handling, speech metrics, context analysis, reports, PDF export, share links, and retries are implemented.
- **Landing visibility:** `frontend/src/main.tsx:17` returns the authentication screen for signed-out visitors before rendering the app's marketing view. Make marketing public, then require authentication for practice, private documents, and reports. Preserve the selected scenario/custom topic through sign-in.
- **Voice readiness:** `App.tsx:485` marks the connection live on socket open. Backend authentication and AssemblyAI connection happen afterward; `server.py:1971` starts STT in the background, and audio is forwarded only while `stt_connected` is true. Introduce an authenticated, provider-ready session event and startup timeout. Show clear startup/failure states and handle STT disconnection.
- **Incomplete preflight:** `PreflightModal.tsx` accepts a backend URL but does not use it. Its enter/skip actions both mark preflight passed. Connect it to authenticated voice readiness checks, distinguish skipped setup from a verified setup, and require microphone access for voice practice. `probe_rime()` currently checks an HTTP client's existence rather than actual provider authorization/speech output.
- **Final-answer risk:** `App.tsx:599` stops capture and immediately sends `end_debate`; `server.py:2081` immediately starts evaluating the current transcript. There is no explicit final-turn flush/wait. Preserve pending capture, drain queued audio, request final endpointing, wait with a bounded timeout, then evaluate a stable transcript. AssemblyAI documents `ForceEndpoint` for forcing a final turn: https://www.assemblyai.com/docs/universal-streaming/turn-detection . This is a source-confirmed protocol mechanism; the user-visible missing-answer failure remains a risk inferred from the current code, not a reproduced live failure.
- **Provider failure honesty:** Rime's fallback can yield silent PCM when Windows SAPI is unavailable, which matters for a Linux deployment. Mock LLM behavior also exists. Production must report unavailable voice/AI services clearly instead of presenting silent or canned fallback output as a working live agent. Provider telemetry currently contains fixed AssemblyAI/Rime names and should reflect actual runtime state.
- **Sample audio:** `MarketingLanding.tsx:89` toggles animation and a timer without starting audio. Replace this with real static sample clips or a non-audio sample-question presentation.
- **Panel claim:** the landing page advertises two-on-one practice, but the normal frontend WebSocket URL does not send `is_panel_mode`. The backend supports it. Avoid featuring it as selectable functionality until wired and verified; this can remain outside the first polishing pass.
- **Deck formats:** direct upload accepts PDF, DOCX/DOC, TXT, MD, and CSV; it does not support native PPTX extraction. Explain "upload your deck as PDF" rather than implying arbitrary presentation upload.
- **Reports:** generated reports have transcript-grounded quote checks, measured speech metrics, coaching, and explicit insufficient-data/fallback handling. Keep that honesty in the UI. PDF and user-created share links exist. No report email sender was found; the HTML meeting summary is formatting, not email delivery.
- **Retry compatibility:** rematch speech input uses browser `SpeechRecognition`, with a typed fallback. It is not the AssemblyAI live stream. Verify that fallback in the browser; reusing AssemblyAI for voice retries is a later improvement unless essential to the demo.

## Landing and UI direction

Keep Miles' existing green identity, logo docking, and light scroll reveals. Use one clear hero explanation, for example:

> Practice difficult conversations before they matter.
>
> Miles is your AI voice sparring partner for pitches, interviews, negotiations, and tough questions. Practice out loud, handle realistic pushback, and leave with a report showing what to improve.

Use an equally weighted scenario grid. Explain the journey: choose a scenario; optionally add a PDF or notes; check audio and practise with Miles; finish and receive feedback. Use VC examples within the pitch card, alongside equally concrete examples for other scenarios.

Show a labelled sample report: clarity, pace/fillers, transcript-backed strengths and weaknesses, better answer examples, next practice steps, and PDF export. Distinguish illustrative values from real session results. Use one primary "Start practicing" action and a secondary "See a sample report" action.

Animation should explain the product: a short transcript exchange, a responding waveform, and a report preview reveal. Keep transform/opacity motion, reduced-motion support, keyboard access, and content visible when animation APIs are unavailable. Review phone layouts, dialog focus/scrolling, microphone status, subtitles, and a clear "Finish & get report" button.

## Implementation order and acceptance

1. Add reversible Meet gates, cover every UI entry point and backend creation/bridge path, and document deployment values.
2. Fix provider-ready startup, meaningful preflight, runtime failures, and final transcript/report completion. Add regression checks for those state transitions and disabled Meet behavior.
3. Make the landing page public; polish messaging, equally weighted scenarios, honest sample content, lightweight animation, and live/report UI.
4. Run the backend suite and TypeScript/build checks. Complete a signed-in spoken round for every scenario, with and without supported context, and verify final-answer inclusion, interruptions, report retrieval, PDF export, and intentional sharing.
5. Check microphone denial, provider failure, authentication expiry, disconnects, no-speech reports, mobile layouts, keyboard use, and reduced motion. Verify the exact deployed frontend/backend configuration, production database migration/runtime role, allowed origins, and WebSocket support. Active voice sessions remain process-local; use one backend process for this release.

Expected implementation files: `src/config.py`, `src/api/server.py`, `src/voice/assemblyai_stream.py`, `src/voice/rime_stream.py`, relevant debate report code, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/audio.ts`, `MarketingLanding.tsx`, `PreflightModal.tsx`, `DebriefModal.tsx`, `styles.css`, Google integration gating, environment examples, and targeted tests. A small shared frontend feature configuration file may be added. Meeting modules remain in the repository.

## Verification completed

- `python -m pytest -q`: **135 passed**, 86.31 seconds.
- `npm.cmd run build`: **passed**, including `tsc --noEmit` and Vite production build.
- No separate lint or frontend automated-test script exists in the current package.
- Repository was clean before this review. This document is the only intended repository addition.
- Browser inspection attempted against the local Vite preview, but access was denied because the admin-enforced browser policy could not be verified. No bypass attempted.
- No explicit live provider smoke check, authenticated browser journey, spoken microphone round, or production deployment verification was completed. Passing local tests/build does not prove those flows.

## Open choice

The user confirmed equal visibility for all scenarios. Report delivery preference is pending: default recommendation is in-app feedback plus PDF download. Email delivery would add a provider, delivery/retry tracking, and explicit user consent; it should not be promised until implemented and verified. Meet option selection is also pending; the recommendation is the UI/backend feature-switch option.
