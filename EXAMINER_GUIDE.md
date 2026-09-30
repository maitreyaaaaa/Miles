# Miles hackathon demo

Miles is an AI voice sparring partner for practicing difficult conversations before they matter. All eight scenarios are presented equally: VC pitch, salary negotiation, cross-examination, senior interview, sales objections, media crisis, boardroom challenge, and custom debate.

## Demo path

1. Open the public landing page. It explains practice, pressure, feedback, and the final report. Landing conversations and report values are clearly labelled examples.
2. Choose any scenario. For a custom debate, enter a topic. Sign in with Google or an email code through the configured Supabase project. The chosen scenario and topic survive the sign-in callback.
3. Optionally upload context such as a pitch-deck PDF or notes. File selection itself does not start a session.
4. Complete audio setup: allow the microphone, speak until the input indicator responds, play the speaker test and confirm it was heard. Live transcription, speech, and model checks must pass before Start is available.
5. Begin practice. Miles waits for the speech services to be ready before showing the live session. Speak at least three answers to obtain a fuller assessment. You can interrupt the opponent; browser and device conditions affect audible cutoff.
6. Select **Finish & get report**. Miles finishes transcription of the last answer before evaluating confirmed turns. Feedback appears in the app; download its PDF. Report sharing is an explicit **Create share link** action, and anyone with the link can read it.

## What to explain

- AssemblyAI supplies live streaming speech recognition. The application uses its turn endpointing and word timing where available.
- The configured language model generates the opponent's replies and evaluates the confirmed transcript. Rime supplies streaming speech output.
- Reports distinguish observed speech signals from AI assessment. A short conversation is labelled limited data. No transcribed answers produces no score; evaluator failure produces unscored rule-based feedback.
- There is no automatic email delivery. Reports are available in-app, as a PDF, and through a link created by the user.
- Google Meet is hidden and disabled for this release; the integration code is retained. Google sign-in remains available. Google Drive requires its separate configured consent.

## Required release checks

Use a deployed frontend and a backend that supports WebSockets, with matching Supabase Auth settings, exact allowed origins, provider keys, and migrated PostgreSQL storage. Run one backend process. Both Meet flags must be false for this release; rebuilding the frontend removes the meeting bridge page from the production output.

Before submission, verify the deployed path with a dedicated account: sign-in, scenario selection, microphone capture, audible replies, interruption, three answers, final report, PDF, reload/retrieve saved report, and intentional sharing. Check desktop and mobile layouts and reduced-motion behavior.

Automated tests and live synthetic-speech checks are recorded in [release verification](Application/docs/hackathon-release-verification-2026-09-30.md). They do not establish browser playback, hosted authentication, database migrations, or a successful deployed user journey.

Setup: [README](README.md), [authentication](Application/docs/authentication.md), [data storage](Application/docs/data-storage.md).
