-- Private application data is accessed only through the FastAPI backend.
-- Runtime code SET LOCAL ROLEs to authenticated/anon and sets a transaction-
-- local miles.user_id or miles.public_share_id before every query.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'miles_runtime') THEN
    CREATE ROLE miles_runtime
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
  END IF;
END
$$;

GRANT anon, authenticated TO miles_runtime;
GRANT USAGE ON SCHEMA public TO anon, authenticated;

CREATE TABLE public.user_contexts (
  owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  context_id text NOT NULL CHECK (context_id ~ '^[A-Za-z0-9_-]{1,64}$'),
  dossier jsonb NOT NULL CHECK (jsonb_typeof(dossier) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_id, context_id)
);

CREATE INDEX user_contexts_owner_created_idx
  ON public.user_contexts (owner_id, created_at DESC);

CREATE TABLE public.meeting_sessions (
  meeting_id text PRIMARY KEY CHECK (meeting_id ~ '^[A-Za-z0-9_-]{1,64}$'),
  owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  session_data jsonb NOT NULL CHECK (jsonb_typeof(session_data) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX meeting_sessions_owner_created_idx
  ON public.meeting_sessions (owner_id, created_at DESC);

CREATE TABLE public.debate_reports (
  owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  session_id text NOT NULL CHECK (session_id ~ '^[A-Za-z0-9_-]{1,64}$'),
  report jsonb NOT NULL CHECK (jsonb_typeof(report) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_id, session_id)
);

CREATE INDEX debate_reports_owner_created_idx
  ON public.debate_reports (owner_id, created_at DESC);

CREATE TABLE public.debrief_shares (
  share_id text PRIMARY KEY CHECK (share_id ~ '^deb_[A-Za-z0-9_-]{1,64}$'),
  owner_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  report jsonb NOT NULL CHECK (jsonb_typeof(report) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.user_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_contexts FORCE ROW LEVEL SECURITY;
ALTER TABLE public.meeting_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meeting_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE public.debate_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.debate_reports FORCE ROW LEVEL SECURITY;
ALTER TABLE public.debrief_shares ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.debrief_shares FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.user_contexts, public.meeting_sessions,
  public.debate_reports, public.debrief_shares FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.user_contexts,
  public.meeting_sessions, public.debate_reports, public.debrief_shares TO authenticated;
GRANT SELECT ON TABLE public.debrief_shares TO anon;

CREATE POLICY user_contexts_owner_access ON public.user_contexts
  FOR ALL TO authenticated
  USING (owner_id = NULLIF(current_setting('miles.user_id', true), '')::uuid)
  WITH CHECK (owner_id = NULLIF(current_setting('miles.user_id', true), '')::uuid);

CREATE POLICY meeting_sessions_owner_access ON public.meeting_sessions
  FOR ALL TO authenticated
  USING (owner_id = NULLIF(current_setting('miles.user_id', true), '')::uuid)
  WITH CHECK (owner_id = NULLIF(current_setting('miles.user_id', true), '')::uuid);

CREATE POLICY debate_reports_owner_access ON public.debate_reports
  FOR ALL TO authenticated
  USING (owner_id = NULLIF(current_setting('miles.user_id', true), '')::uuid)
  WITH CHECK (owner_id = NULLIF(current_setting('miles.user_id', true), '')::uuid);

CREATE POLICY debrief_shares_owner_access ON public.debrief_shares
  FOR ALL TO authenticated
  USING (owner_id = NULLIF(current_setting('miles.user_id', true), '')::uuid)
  WITH CHECK (owner_id = NULLIF(current_setting('miles.user_id', true), '')::uuid);

CREATE POLICY debrief_shares_capability_read ON public.debrief_shares
  FOR SELECT TO anon
  USING (share_id = NULLIF(current_setting('miles.public_share_id', true), ''));
