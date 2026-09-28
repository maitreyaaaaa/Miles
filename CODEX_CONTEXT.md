# Miles architecture context

Use this note to orient work, then verify behavior in the source code. Older hackathon latency and feature claims have been removed; they are not evidence of current behavior.

- `Application/main.py` starts one FastAPI/Uvicorn listener using `HOST` and `PORT`.
- `Application/src/api/server.py` defines the REST and WebSocket API. Its handlers are currently in one large module; follow the existing route and WebSocket code when changing contracts.
- `Application/src/debate/` contains debate logic; `Application/src/voice/` contains AssemblyAI, Rime, and interruption handling; `Application/src/context/` contains uploads and Google Drive operations; `Application/src/meeting/` contains Google Calendar/Meet and Recall.ai lifecycle operations.
- `Application/frontend/src/App.tsx` owns the main UI and WebSocket contract; `Application/frontend/src/audio.ts` handles browser microphone capture and audio playback.
- Google Drive, Google Calendar, AssemblyAI, Rime, and Recall.ai remain active optional integrations. Recall bot lifecycle is implemented, but its audio and transcript stream is not connected to Miles' live sparring engine.
- JSON storage defaults to `Application/data/`; `MILES_DATA_DIR` selects another root. Use a temporary directory for tests.
- The API has no application-level login or owner-scoped data access; treat it as a trusted single-user service.
- Automated backend tests are in `Application/tests/`. Provider smoke checks and the cancellation benchmark require explicit `--live` opt-in because they can call external services.

See [README.md](README.md) for setup and verification. The duplicated copy under `Application/` points back here.
