# Supabase setup verification — 2026-09-30

Target project: `abpaquttwwaaahymkdwn` (`https://abpaquttwwaaahymkdwn.supabase.co`).

## Database

- Applied the repository's `20260927000000_user_data.sql` atomically and recorded its version in Supabase migration history.
- Verified the four tables: `user_contexts`, `meeting_sessions`, `debate_reports`, and `debrief_shares`.
- Verified forced row-level security, owner policies, share-capability policy, foreign keys, and indexes. Anonymous users cannot select private reports.
- Provisioned `miles_runtime` with a random password, preserving its restricted privileges and non-inherited role memberships.
- A real `PostgresDatabase.check()` through the Supavisor transaction pooler passed schema and runtime-role checks.
- Fixed the provisioning script: Supabase's postgres operator cannot repeat superuser-only attributes in `ALTER ROLE`. The script now checks the existing role's privileges before changing only its login and password.
- The password backup is encrypted with Windows DPAPI outside the repository. No credentials are included in this document.

## Authentication

- The release uses Google sign-in only. Email sign-in is removed from the UI and disabled in the new project's Auth configuration.
- Google is enabled with the existing web OAuth credentials; provider settings were read back successfully.
- Site URL: `https://miles-one-nu.vercel.app`.
- Frontend redirect allowlist: `https://miles-one-nu.vercel.app/auth/callback` and `http://localhost:5173/auth/callback`.
- The public JWKS endpoint returned HTTP 200 with an ES256 key compatible with the backend verifier.
- A live OAuth initiation returned HTTP 302 from Supabase to Google. Google then rejected the request with `redirect_uri_mismatch`.
- Required Google Cloud change: add `https://abpaquttwwaaahymkdwn.supabase.co/auth/v1/callback` to the existing web client's authorized redirect URIs. A successful authorization-code exchange and signed-in session are still unverified.

## Checks

- Backend suite: 166 passed, including restricted-role provisioning and storage checks.
- Frontend product-flow tests: 7 passed, including Google-only sign-in markup and protected arena access.
- Frontend build, including TypeScript check: passed.
- These checks do not establish browser, microphone, voice-provider, or authenticated hosted-session acceptance.

## Remaining hosted setup

Vercel and Railway management connections are not authenticated yet. Their hosted variables have not been changed in this setup pass.

- Vercel: set `VITE_SUPABASE_URL` and the public publishable key in `VITE_SUPABASE_ANON_KEY`, then rebuild.
- Railway: set `SUPABASE_URL`, the restricted runtime `DATABASE_URL`, `APP_ENV=production`, and the exact frontend origin in `ALLOWED_ORIGINS`. Preserve provider credentials and `GOOGLE_MEET_ENABLED=false`.
- Verify the deployed revision, healthy backend, protected API responses, CORS, Google sign-in, and an authenticated voice session/report flow.
- Rotate the Supabase credentials previously shared in chat after setup. They are not stored in Git or this verification record.
