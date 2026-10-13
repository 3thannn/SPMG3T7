-- US14.1: a Coordinator requests one or more venue bookings for an event.
-- Apply once to an existing Supabase project before deploying the
-- /events/{id}/bookings routes. Safe to run repeatedly: every statement is
-- IF NOT EXISTS or otherwise idempotent.
--
-- One row per venue an event asks for, so a main hall and two breakout rooms
-- are three rows against one event (Week 7 change #3).
--
-- The story asks for a single venue column on `events` to be migrated here if
-- US6.2's schema had one. It never did: `events` has no venue column in
-- SUPABASE_SETUP.sql or in any script since, so there is nothing to move.

-- Only the status this story produces. The Venue Booking Approval epic adds the
-- ones Venue Staff move a booking to, with ALTER TYPE ... ADD VALUE.
DO $$
BEGIN
    CREATE TYPE public.booking_status AS ENUM ('Requested');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS public.venue_bookings (
    id SERIAL PRIMARY KEY,
    -- A booking means nothing without its event, as with status_changes.
    event_id INTEGER NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
    -- No cascade: deleting a venue must not quietly take an event's booking
    -- with it. The API refuses to delete a booked venue with a 409; this is
    -- what stops a delete made some other way.
    venue_id INTEGER NOT NULL REFERENCES public.venues(id),
    start_at TIMESTAMP NOT NULL,
    end_at TIMESTAMP NOT NULL,
    status public.booking_status NOT NULL DEFAULT 'Requested',
    -- Who asked. SET NULL so removing a user keeps the booking on record.
    requested_by_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    -- The API refuses this first with a message; the constraint means a row
    -- written some other way cannot break the rule either.
    CONSTRAINT venue_bookings_end_after_start CHECK (end_at > start_at)
);

-- The read path: an event's bookings, soonest first.
CREATE INDEX IF NOT EXISTS ix_venue_bookings_event_start
    ON public.venue_bookings (event_id, start_at);
-- Whether a venue has any bookings, asked before it is deleted.
CREATE INDEX IF NOT EXISTS ix_venue_bookings_venue_id
    ON public.venue_bookings (venue_id);
CREATE INDEX IF NOT EXISTS ix_venue_bookings_requested_by_id
    ON public.venue_bookings (requested_by_id);

-- Server-only access, as for every other table (see SUPABASE_HARDENING.sql).
ALTER TABLE public.venue_bookings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.venue_bookings FROM anon, authenticated;

-- Verify the table is there with the expected columns.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venue_bookings'
ORDER BY ordinal_position;
