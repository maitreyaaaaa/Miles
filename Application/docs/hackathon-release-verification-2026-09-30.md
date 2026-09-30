# Sparring-only release verification — 2026-09-30

## Implemented scope

- Google Meet retained behind opt-in frontend/backend flags, default false. UI entry points and the meeting bridge build are hidden; creation, launch, calendar consent, and bridge connection are blocked server-side. Google sign-in and Drive remain separate.
- Public landing page before authentication, eight equally presented scenarios, clear practice-to-report explanation, illustrative conversation/report examples, and restrained motion with reduced-motion support.
- Scenario/topic preserved across authentication. Context upload described as PDF/notes; no unsupported presentation-file or panel-mode promises.
- Preflight requires measured microphone activity, confirmed speaker test, and successful speech/model probes. Session readiness waits for AssemblyAI Begin and live provider readiness.
- Live provider failures surface errors instead of silently simulating conversation/speech. Final transcription is flushed before assessment. Reports distinguish short, empty, AI-evaluated, and unscored fallback sessions.
- Report evaluation has a 45-second limit. A save failure warns the user and retains temporary PDF recovery without blocking another session. Temporary reports are bounded to 50 after each session closes, in one process.
- Report creation stays in-app with PDF and explicit sharing; no email-delivery claim.

## Evidence

- Backend regression suite covers disabled Meet actions, retained integration paths, authentication/ownership, provider readiness and startup failure, all eight scenario flows, final-transcript ordering, report/PDF output, provider-failure honesty, evaluator timeout, and storage-failure recovery. Test providers are explicit doubles; pytest never calls live providers.
- Frontend tests render actual components and verify the public landing, equal scenario visibility, absent Meet/fake audio controls, truthful example labels, login gating, and preserved practice intent. This is markup verification, not browser verification.
- Production frontend build includes TypeScript checking. Default output omits `meeting-bridge.html`.
- Live provider smoke check passed AssemblyAI Begin, nonzero Rime PCM, and configured model response.
- Live synthetic-speech pipeline passed all eight scenarios plus one pitch with synthetic context. Every flow produced live transcription, model reply, speech output, AI assessment and PDF. One-answer assessments correctly indicated limited data. Results: ignored local `data/demo-flow-results.json`.
- A three-answer live synthetic pitch also passed: complete AI assessment and valid PDF. Results: ignored local `data/demo-full-round-results.json`. It uses a repeated synthetic answer to exercise the full-session report state, not to assess human coaching quality.
- Final backend suite: **157 passed**. Frontend markup tests: **6 passed**. TypeScript and production build: **passed**. Git whitespace check: **passed** (Windows CRLF accounted for). Default build contains no meeting bridge page.

## Remaining acceptance boundaries

Local provider keys work, but local Supabase frontend/backend settings and PostgreSQL connection are absent. No authentication bypass was added. A deployed endpoint/configuration is needed to verify authenticated practice and durable hosted storage.

The browser automation tool was denied because its administrator policy could not be verified. No browser visual, real microphone/playback, mobile, or deployed end-to-end acceptance is claimed. SSR tests and nonzero synthetic PCM are separate evidence.

Read-only hosting inspection found the production frontend at `https://miles-one-nu.vercel.app`, still on commit `a6aeaaa9c7c26ce2c01ca8c610c4fd12c801e129`. Its current compiled API host is `https://miles-production-e65e.up.railway.app`. The landing returned HTTP 200; that does not verify authentication or UI behavior. Current changes are local and are not included in that deployment.

The compiled Railway host returned **HTTP 502** for `/health`, `/api/capabilities`, and `/api/scenarios`; a follow-up request also returned 502 from Railway's edge. Cause is unverified. The native Railway plugin is installed and enabled, but project and identity requests returned `USER_NOT_LOGGED_IN`; the separate Composio connection also remained pending. Hosted logs and backend recovery require authenticated Railway access.

The user authorized committing and pushing these changes to `main` after local validation. This document records pre-deployment evidence; a successful push does not establish hosted acceptance. No manual deployment, database migration, external bot cleanup, or public report creation was performed during the implementation review.

## Release sequence

1. Configure matching frontend/backend Supabase settings, production database runtime URL and applied schema, exact CORS origins, voice/model keys, one backend process, and false Meet flags.
2. Deploy the same reviewed revision of frontend and backend. Confirm public landing and authentication callbacks.
3. Execute the examiner path on the deployed build with a dedicated account and browser microphone. Verify saved-report retrieval, PDF, owned data boundaries and optional explicit sharing.
4. Record endpoint/revision, observed browser results, and any limitations before calling the submission ready.

## Changed files

- `Application/.env.example`
- `Application/docs/hackathon-readiness-review-2026-09-30.md`
- `Application/docs/hackathon-release-verification-2026-09-30.md`
- `Application/frontend/.env.example`
- `Application/frontend/package.json`
- `Application/frontend/src/App.tsx`
- `Application/frontend/src/AppRoot.tsx`
- `Application/frontend/src/audio.ts`
- `Application/frontend/src/components/AuthScreen.tsx`
- `Application/frontend/src/components/DebriefModal.tsx`
- `Application/frontend/src/components/DominanceHUD.tsx`
- `Application/frontend/src/components/MarketingLanding.tsx`
- `Application/frontend/src/components/PreflightModal.tsx`
- `Application/frontend/src/features.ts`
- `Application/frontend/src/main.tsx`
- `Application/frontend/src/practice.css`
- `Application/frontend/src/practiceIntent.ts`
- `Application/frontend/src/scenarios.ts`
- `Application/frontend/src/types.ts`
- `Application/frontend/tests/product-flow.test.mjs`
- `Application/frontend/vite.config.ts`
- `Application/scripts/provider_smoke_check.py`
- `Application/scripts/verify_demo_flow.py`
- `Application/src/api/server.py`
- `Application/src/config.py`
- `Application/src/debate/engine.py`
- `Application/src/debate/llm_client.py`
- `Application/src/meeting/meeting_engine.py`
- `Application/src/voice/assemblyai_stream.py`
- `Application/src/voice/errors.py`
- `Application/src/voice/rime_stream.py`
- `Application/tests/conftest.py`
- `Application/tests/test_demo_readiness.py`
- `Application/tests/test_meeting_engine.py`
- `Application/tests/test_recall_integration.py`
- `Application/tests/test_server.py`
- `EXAMINER_GUIDE.md`
- `README.md`
