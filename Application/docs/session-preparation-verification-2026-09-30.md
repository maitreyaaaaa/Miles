# Session preparation UI — 2026-09-30

## Behavior

Every sparring start entry point now opens document preparation before requesting microphone access or starting the voice session:

1. Choose a scenario or custom topic and click **Start sparring session**.
2. Optionally add a pitch deck, CV, or notes. Slide decks should be exported as PDF; supported uploads are PDF, DOCX, TXT, Markdown, and CSV.
3. Analyze the document and select **Use this document** to attach it. Closing upload returns to preparation; unconfirmed documents are not attached.
4. Review, replace, or remove an attached document, or continue without one.
5. Complete the existing audio and voice-service checks, then start practice. The existing session request includes the selected document's `context_id`.

The top-right deck shortcut is removed. All eight scenarios keep the same optional document flow. Standalone audio setup closes after checking audio and does not start a session.

## UI fixes

- Dialogs open one at a time and retain the existing focus trap, Escape behavior, and scroll lock.
- Document previews reset to the actual selected context when reopened, avoiding stale attachments after removal or cancellation.
- Upload actions cannot dismiss the dialog during processing; document requests have a 90-second timeout with a retry message.
- Selecting the same file again is supported. Legacy `.doc` is excluded from the browser file picker; use DOCX or PDF.
- Preparation actions stack on small screens; audio error badges wrap; document tabs scroll horizontally.
- The arena overview logo is now a keyboard-accessible button.

## Validation

- Frontend product-flow suite: **13 passed**. Actual components were rendered with React SSR; preparation transitions, upload return, cancellation, audio gates, optional documents across all scenarios, and the removed navigation shortcut were checked.
- Backend document/context tests: **15 passed** (`test_context_debate.py`, `test_context_extractor.py`, `test_context_analyzer.py`).
- TypeScript check and production Vite build: **passed**.
- Git whitespace/diff check: **passed**.

These are code, state-transition, and markup checks. Browser visual inspection was blocked because the browser tool could not verify the admin-enforced policy. No browser security workaround was attempted. Signed-in document upload, mobile visual appearance, microphone audio, and a complete production voice/report session are still unverified in a browser.
