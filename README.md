# Miles

Miles is a voice sparring app with a FastAPI backend and a React frontend. It runs a spoken debate, scores the conversation, and saves reports and meeting records locally.

## What is in the repository

- `Application/src/` — Python API, debate engine, speech providers, Google integrations, and meeting lifecycle.
- `Application/frontend/` — React and TypeScript app.
- `Application/tests/` — automated backend tests. Provider calls are not part of pytest discovery.
- `Application/docs/` and the root planning documents — older design notes; check the code and this README for current behavior.

## Integrations

- **Speech:** AssemblyAI streaming transcription and Rime streaming speech are optional. The app has local fallbacks when provider keys are not configured.
- **Language models:** OpenAI, Gemini, and Anthropic are supported, with a local mock fallback.
- **Google Drive:** imports context documents and can export debriefs when Google credentials are configured.
- **Google Calendar / Meet:** provisions calendar events and meeting links when Google credentials are configured.
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

The optional provider smoke check calls AssemblyAI and Rime and may use provider quota. Run it only when intended:

```powershell
python scripts/provider_smoke_check.py --live
```

`python benchmark_interruption.py --live` also streams speech through the configured TTS provider. It measures simulated server-side cancellation response only. It does not measure microphone detection, browser playback buffers, or end-to-end audible cutoff; see [`Application/RIME_EVIDENCE.md`](Application/RIME_EVIDENCE.md).

## Local data

JSON data used by local development defaults to `Application/data/`. Set `MILES_DATA_DIR` to select another directory or to point the explicit legacy importer at existing files. Docker build contexts exclude `.env`, local data, caches, and dependency folders.

See [`Application/docs/data-storage.md`](Application/docs/data-storage.md) for schema setup, runtime database credentials, and the safe JSON import process.
