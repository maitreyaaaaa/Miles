# Recall.ai meeting bot setup

Miles uses Recall Output Media as its live audio bridge. Recall loads a small webpage hosted by the frontend, gives that page the meeting audio, and streams the page's generated speech back into the meeting. The page connects to the FastAPI WebSocket; AssemblyAI, the configured LLM, and Rime handle live turns. Signed Recall status webhooks update the stored meeting status and debrief lifecycle.

## Required deployment settings

Configure these values on the backend only:

- `RECALL_AI_API_KEY` and `RECALL_AI_REGION`
- `RECALL_AI_WEBHOOK_SECRET` from the Recall workspace verification settings. For workspaces created before 2025-12-15, use the per-endpoint `RECALL_AI_SVIX_WEBHOOK_SECRET` when required by Recall.
- `RECALL_AUDIO_BRIDGE_URL`, set to the public Vercel page, for example `https://your-app.vercel.app/meeting-bridge.html`
- `RECALL_AUDIO_BRIDGE_SECRET`, a random secret with at least 32 characters. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `ASSEMBLYAI_API_KEY`, `RIME_API_KEY`, and at least one of `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `ANTHROPIC_API_KEY`
- `ALLOWED_ORIGINS` must include the exact HTTPS origin that serves `RECALL_AUDIO_BRIDGE_URL`.

Set the frontend `VITE_BACKEND_URL` to the public FastAPI origin, then rebuild and deploy the Vercel frontend. The backend host must support ASGI WebSockets and long-lived connections; Vercel static hosting serves the bridge page but is not the voice-session server. Keep one backend process while live sessions are held in process memory.

In the Recall dashboard, configure the bot status change webhook to `https://your-api.example.com/api/webhook/recall` and subscribe to bot status changes. Use the matching region and verification secret. Recall retries failed webhook deliveries, so the endpoint verifies the raw body signature before changing a meeting record.

## Runtime behavior and limits

- A successful launch response means Recall accepted a bot request. The UI reports a real join only after a signed webhook says the bot entered the call. `in_waiting_room` means a meeting host still needs to admit it; `fatal` records a failure.
- Bridge tickets are signed, scoped to one owner and meeting, expire after the meeting window, and are never sent to the browser app's authentication client.
- Recall Output Media always streams a visual webpage feed as camera video or screenshare. This integration uses a branded camera feed; it cannot provide a truly audio-only interactive bot.
- Ad-hoc bots may take time to join. Schedule at least ten minutes ahead when you need Recall's scheduled-bot warm-up guarantee. The app accepts schedules up to 30 days ahead.
- Local tests and builds verify request shape, ticket authentication, webhook state handling, and the browser bundle. They do not prove an external bot can enter a real meeting. Live acceptance requires configured provider credentials, a publicly reachable API and Vercel page, webhook delivery, and a test meeting where the bot can be admitted.
