-- Apply once to an existing Supabase project before deploying partial drafts.
-- Safe to run repeatedly: PostgreSQL treats dropping an absent constraint as a no-op.
ALTER TABLE public.events
ALTER COLUMN proposed_date DROP NOT NULL;
