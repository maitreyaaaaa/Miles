# PostgreSQL storage setup

Production uses the Supabase project's PostgreSQL database for contexts, meeting sessions, private debate reports, and debrief share links. Local development without `DATABASE_URL` continues to use JSON files. The API refuses to start in production without the database URL.

The SQL migration creates owner-scoped tables, indexes, RLS policies, and a non-login `miles_runtime` role. The API connects as that restricted role, then uses transaction-local `SET LOCAL ROLE authenticated` or `anon` and a transaction-local owner/share context for each operation. The role and context reset at transaction end, which is compatible with Supabase's transaction pooler. Browser clients receive no database credentials and the public Data API cannot set Miles' private owner context.

## Apply the schema

Use a staging Supabase project first. Back up the target project before applying schema or data changes.

```powershell
cd Application
supabase login
supabase link --project-ref <project-ref>
supabase db push --dry-run
supabase db push
```

The migration is additive. It does not delete or reassign existing records. The Supabase CLI tracks applied migration versions; do not edit an already-applied migration. Add a new migration for later schema changes.

## Create the runtime login

Migration credentials are operator-only. Keep `MILES_MIGRATION_DATABASE_URL` and `MILES_RUNTIME_DB_PASSWORD` out of the backend service environment and `.env` files; inject them into a short-lived, secured operator environment. Generate a random runtime password with at least 32 characters, set both values there, and run:

```powershell
python scripts/configure_postgres_runtime_role.py
```

The script changes the role password without printing either credential. Configure the backend's `DATABASE_URL` with the Supabase pooler URL for the `miles_runtime` role, `sslmode=require`, and the generated password. With Supavisor's shared transaction pooler, the username format is `miles_runtime.<project-ref>`. URL-encode special characters in the password. Set `DATABASE_POOL_MAX_SIZE` to a value that fits the project's database connection limit.

Keep the direct administrative URL out of the running API service after migrations, role setup, and any data import. The API needs only `DATABASE_URL` and `SUPABASE_URL`.

## Import existing JSON data

The importer previews files and counts by default. It never edits or deletes the source files. It only imports contexts and meetings with a valid owner ID, private reports beneath a valid owner directory, and share links with their existing capability IDs. It does not assign unowned records to a user. Owner IDs must already exist in the target Supabase Auth project; otherwise the import stops before writing anything.

Point `MILES_DATA_DIR` to the old data directory, apply the schema first, then preview and import:

```powershell
$env:MILES_DATA_DIR = "D:\path\to\existing\miles-data"
python -m src.storage.migrate_legacy
python -m src.storage.migrate_legacy --apply
```

`--apply` uses `MILES_MIGRATION_DATABASE_URL`, which must be a direct administrative database URL. The importer runs in one transaction, preserves conflicting database rows, reports counts only, and leaves the JSON source untouched. Resolve accounts that were not migrated into this Auth project before retrying.

## Deployment boundary

PostgreSQL now holds durable user records and is shared across API processes. Active debate engines and live meeting coordinators still live in process memory. Keep one backend process until those real-time sessions have a shared coordinator. Database backups and Supabase point-in-time recovery should be enabled before accepting production data.

If a deployment must be rolled back, retain the source JSON and the database snapshot. The migration does not provide a destructive down migration; restore the previous application only after confirming it can read the active data, or roll forward with a fix.
