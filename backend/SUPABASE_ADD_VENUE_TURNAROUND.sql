-- US9.4: each venue has a setup time and a turnaround time, in whole minutes.
-- Apply once to an existing Supabase project before deploying US9.4. Safe to
-- run repeatedly: IF NOT EXISTS and DROP ... IF EXISTS make a second run a no-op.
--
-- Every venue read selects these columns, so without them all five /venues
-- routes return 500.
--
-- NOT NULL DEFAULT 0: the story's default, and what every venue that predates
-- this script gets. 0 is a real answer ("no setup needed"), so there is no
-- separate "not set" state to keep apart from it.
ALTER TABLE public.venues
    ADD COLUMN IF NOT EXISTS setup_minutes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.venues
    ADD COLUMN IF NOT EXISTS turnaround_minutes INTEGER NOT NULL DEFAULT 0;

-- The API refuses these first with a message; the constraints mean a row
-- written some other way cannot break the rule either. The 1440-minute (24 h)
-- ceiling is a team-chosen default, not customer-confirmed.
ALTER TABLE public.venues
    DROP CONSTRAINT IF EXISTS venues_setup_minutes_range;
ALTER TABLE public.venues
    ADD CONSTRAINT venues_setup_minutes_range
    CHECK (setup_minutes BETWEEN 0 AND 1440);
ALTER TABLE public.venues
    DROP CONSTRAINT IF EXISTS venues_turnaround_minutes_range;
ALTER TABLE public.venues
    ADD CONSTRAINT venues_turnaround_minutes_range
    CHECK (turnaround_minutes BETWEEN 0 AND 1440);

-- US9.4's re-check reads a venue's bookings by venue, which
-- ix_venue_bookings_venue_id (SUPABASE_ADD_VENUE_BOOKINGS.sql) already serves.

-- Verify the new columns.
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venues'
  AND column_name IN ('setup_minutes', 'turnaround_minutes');
