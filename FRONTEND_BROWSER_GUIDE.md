# Frontend integration notes

The browser code is implemented. These files are the source of truth for its current contracts:

- `Application/frontend/src/audio.ts` — microphone capture, PCM framing, and local playback.
- `Application/frontend/src/App.tsx` — WebSocket URL, message handling, and main UI flow.
- `Application/src/api/server.py` — backend WebSocket and REST contracts.

Read both client and server before changing a message shape. This avoids copying old examples that no longer match the implementation. The microphone path currently uses `ScriptProcessorNode`; changes to that capture path need cross-browser verification.

The optional Google and Recall flows are described in the repository [README](README.md). Recall bot lifecycle is active, but meeting audio and transcripts are not bridged to the live sparring loop.
