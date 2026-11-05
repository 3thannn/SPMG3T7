-- US5.2: the log of changes made to an event (event_changes) and its change_type.
--
-- Both were first created on the live database only. Every later script writes
-- to the table (US5.2's Coordinator edits, US11.1/US11.2's accepted change
-- requests, US2.1's needs) and casts to the type, so a database built from this
-- repo failed at SUPABASE_US11_2_CHANGE_REVIEW.sql ('type "public.change_type"
-- does not exist'; CI's fresh-install build, A3). This is the committed version,
-- with the columns those scripts and app/event_store.py use.
--
-- Created only where missing, so the live database keeps its own. Apply after
-- SUPABASE_SETUP.sql and before SUPABASE_ADD_CHANGE_REQUESTS.sql. Safe to run
-- repeatedly.

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type
        WHERE typname = 'change_type' AND typnamespace = 'public'::regnamespace
    ) THEN
        CREATE TYPE public.change_type AS ENUM ('important', 'routine');
    END IF;
END $$;

-- One row per field changed. `important` marks date/time, attendance, venue and
-- equipment changes (US5.2), which send a Confirmed event back to Planning
-- (US11.3). Times are naive UTC, like every other recorded time.
CREATE TABLE IF NOT EXISTS public.event_changes (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
    changed_field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_type public.change_type NOT NULL,
    changed_by_user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT timezone('UTC', now())
);

CREATE INDEX IF NOT EXISTS ix_event_changes_event_id ON public.event_changes (event_id);

-- Only the backend's service role reads and writes it, as with the other tables.
ALTER TABLE public.event_changes ENABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';
