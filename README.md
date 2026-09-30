# Miles

Miles helps people practice difficult conversations with an AI voice sparring partner: pitches, interviews, negotiations, sales objections, cross-examination, crisis communication, boardroom challenges, and custom topics. After practice, it provides feedback, a downloadable PDF, and optional explicit report sharing. The backend is FastAPI and the frontend is React.

## What is in the repository

- `Application/src/` — Python API, debate engine, speech providers, Google integrations, and meeting lifecycle.
- `Application/frontend/` — React and TypeScript app.
- `Application/tests/` — automated backend tests. Provider calls are not part of pytest discovery.
- `Application/docs/` and the root planning documents — older design notes; check the code and this README for current behavior.

## Integrations

- **Speech:** Live voice practice requires AssemblyAI streaming transcription and Rime streaming speech. Missing or failed providers are shown as unavailable; production sessions do not silently use simulated speech.
- **Language models:** OpenAI, Gemini, and Anthropic are supported. Live practice requires a configured provider. Explicit mock providers remain available to deterministic tests. If report evaluation fails, feedback is labelled as rule-based and argument quality remains unscored.
- **Google Drive:** imports context documents and can export debriefs when Google credentials are configured.
- **Google Calendar / Meet:** preserved but disabled by default for the hackathon release. Enable both backend `GOOGLE_MEET_ENABLED=true` and frontend `VITE_GOOGLE_MEET_ENABLED=true`, then rebuild, to restore the UI and bridge build. Disabled creation, launch, calendar-consent, and audio-bridge paths reject requests before external actions; existing bot lifecycle cleanup remains available.
- **Recall.ai:** creates and schedules cloud bots, streams meeting audio through Recall Output Media into Miles' AssemblyAI/LLM/Rime loop, and tracks lifecycle state through signed webhooks. Live setup is documented in [`Application/docs/meeting-bot.md`](Application/docs/meeting-bot.md). Local development may still use an explicit mock provider.

Live integrations need their provider credentials in `Application/.env`; start from `Application/.env.example`. Never commit `.env` files.

## User accounts and deployment

Miles uses Supabase Auth for Google sign-in and six-digit email codes. Google Drive and Calendar consent remains a separate integration permission. Follow [`Application/docs/authentication.md`](Application/docs/authentication.md) to configure the Supabase project, frontend values, API token verification, and production origin allowlist. The API fails closed when Supabase is not configured.

Production context, meeting, and debrief records use Supabase PostgreSQL with owner keys, row-level security, and a restricted runtime database role. Local development without `DATABASE_URL` keeps JSON storage under `MILES_DATA_DIR`; production startup fails without PostgreSQL. Active voice WebSockets remain in process memory, so run one backend process until shared session coordination is implemented. The API host must support long-lived WebSocket connections.

## Run locally

Use Python 3.12 or newer and Node.js. From `Application/`:

```powershell
pip install -e ".[dev]"
python main.py
```

The API listens on `http://localhost:8000` by default. Set `PORT` to change the listener port. Run the frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

## Check changes

From `Application/`:

```powershell
pytest -q
```

Build the frontend from `Application/frontend/`:

```powershell
npm run build
```

The optional provider smoke check calls AssemblyAI, Rime, and the configured language model and may use provider quota. Run it only when intended:

```powershell
python scripts/provider_smoke_check.py --live
```

Frontend markup tests run with `npm run test` in `Application/frontend/`. These do not replace browser checks. The opt-in synthetic-speech check covers all eight scenarios and one context-backed pitch, including live transcription, opponent response, speech output, and report/PDF generation:

```powershell
python scripts/verify_demo_flow.py --live
python scripts/verify_demo_flow.py --live --scenario vc_pitch --turns 3 --output data/demo-full-round-results.json
```

See [the examiner guide](EXAMINER_GUIDE.md) for the intended demo path and [release verification](Application/docs/hackathon-release-verification-2026-09-30.md) for current evidence and remaining deployment checks.

`python benchmark_interruption.py --live` also streams speech through the configured TTS provider. It measures simulated server-side cancellation response only. It does not measure microphone detection, browser playback buffers, or end-to-end audible cutoff; see [`Application/RIME_EVIDENCE.md`](Application/RIME_EVIDENCE.md).

## Local data

JSON data used by local development defaults to `Application/data/`. Set `MILES_DATA_DIR` to select another directory or to point the explicit legacy importer at existing files. Docker build contexts exclude `.env`, local data, caches, and dependency folders.

See [`Application/docs/data-storage.md`](Application/docs/data-storage.md) for schema setup, runtime database credentials, and the safe JSON import process.
