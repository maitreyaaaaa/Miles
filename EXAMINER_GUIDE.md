# Miles project overview

Miles is a voice sparring app with built-in debate scenarios, optional speech and language-model providers, saved debriefs, and Google integrations.

## Current integration status

- AssemblyAI and Rime are optional providers for the debate voice flow.
- OpenAI, Gemini, and Anthropic are supported language-model providers; a mock provider is available without a key.
- Google Drive supports context import and debrief export when configured.
- Google Calendar can provision events and meeting links when configured.
- Recall.ai controls cloud bot creation and lifecycle. Recall audio and transcripts are not connected to the live sparring engine. The meeting audio channel is currently simulated.

## Architecture

The backend is in `Application/src/`, the React client is in `Application/frontend/`, and backend tests are in `Application/tests/`. The API runs on one configured port. JSON records use `MILES_DATA_DIR` or default to `Application/data/`.

The code includes a cancellation benchmark, but it triggers the cancellation handler directly and measures server-side software response. It does not prove mic-to-speaker latency. See [`Application/RIME_EVIDENCE.md`](Application/RIME_EVIDENCE.md) for its limits.

For setup and checks, use the [repository README](README.md). Design notes in `docs/` and `ROADMAP_ASSEMBLYAI.md` are plans, not a feature checklist.
