-- US12.1: Venue Staff mark date ranges when a venue is unavailable.
-- Apply once to an existing Supabase project before deploying the
-- /venues/{id}/unavailability routes. Safe to run repeatedly: every statement
-- is IF NOT EXISTS or otherwise idempotent.
--
-- One row per blackout period, inclusive at both ends. Overlapping rows are
-- allowed on purpose — a closure and a maintenance window can share days — and
-- nothing checks them against events, because bookings arrive in Sprint 3.
CREATE TABLE IF NOT EXISTS public.venue_unavailability (
    id SERIAL PRIMARY KEY,
    -- A blackout means nothing once its venue is gone, and US9.1c's hard
    -- delete must not start failing because a venue once had a closure.
    venue_id INTEGER NOT NULL REFERENCES public.venues(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT,
    -- Who marked it. SET NULL so removing a user keeps the closure on record.
    created_by_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    -- The API refuses this first with a message; the constraint means a row
    -- written some other way cannot break the rule either.
    CONSTRAINT venue_unavailability_end_not_before_start CHECK (end_date >= start_date)
);

-- The one read path: a venue's ranges, soonest first.
CREATE INDEX IF NOT EXISTS ix_venue_unavailability_venue_start
    ON public.venue_unavailability (venue_id, start_date);
CREATE INDEX IF NOT EXISTS ix_venue_unavailability_created_by_id
    ON public.venue_unavailability (created_by_id);

-- Server-only access, as for every other table (see SUPABASE_HARDENING.sql).
ALTER TABLE public.venue_unavailability ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.venue_unavailability FROM anon, authenticated;

-- Verify the table is there with the expected columns.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venue_unavailability'
ORDER BY ordinal_position;
