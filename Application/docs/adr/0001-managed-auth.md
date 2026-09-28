# ADR 0001: Managed user authentication

- Status: accepted
- Date: 2026-09-27

## Context

Miles is moving from a trusted single-user service to a public app. It needs Google sign-in, email one-time codes, and server-enforced ownership checks without creating a custom email delivery, OTP, or token-issuance system.

## Decision

Use Supabase Auth for Google OAuth and six-digit email OTP. The React app uses Supabase's public client and keeps its session in `sessionStorage`. FastAPI verifies asymmetric Supabase JWTs from the project's JWKS endpoint. The API uses the verified user subject to partition context data and authorize meeting, debate, and report operations. Drive and Calendar authorization remains separate from app sign-in.

## Consequences

- A configured Supabase project is required before app sign-in works.
- Google provider credentials, email templates, OTP expiry, and redirect allowlists are configured in Supabase.
- Backend API secrets remain server-side; the frontend uses only the public key.
- Supabase PostgreSQL stores durable production user records with owner-scoped row-level security. Local JSON stores remain for development and legacy import.
- Live debate engines and meeting coordinators remain process-local, so production runs one backend process until shared live-session coordination is implemented.
- Public debrief links remain intentionally accessible to anyone with the generated share token.
