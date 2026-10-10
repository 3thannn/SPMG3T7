-- US18.1: each venue booking records what it needs of a venue, so the
-- suitability check has something to check.
-- Apply once to an existing Supabase project, after
-- SUPABASE_ADD_VENUE_BOOKINGS.sql and SUPABASE_CANCEL_VENUE_BOOKINGS.sql, and
-- before deploying US18.1. Safe to run repeatedly: every statement is
-- IF NOT EXISTS or otherwise idempotent.
--
-- The headcount is per booking, not the event's: a breakout room in a
-- multi-venue event (Week 7 change #3) is checked against the people in that
-- room, not against the whole event's attendance.

-- Nullable only for bookings made before this script whose event has no
-- attendance to copy; the API always writes one.
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS headcount INTEGER;
-- NULL when the booking asks for no particular layout.
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS required_layout TEXT;
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS required_facilities TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS accessibility_needs TEXT[] NOT NULL DEFAULT '{}';

-- Bookings made before this script default to their event's attendance, which
-- is what the story says a booking's headcount defaults to.
UPDATE public.venue_bookings AS booking
SET headcount = event.expected_attendance
FROM public.events AS event
WHERE booking.event_id = event.id
  AND booking.headcount IS NULL
  AND event.expected_attendance >= 1;

-- The API refuses this first with a message; the constraint means a row
-- written some other way cannot break the rule either.
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_headcount_positive;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_headcount_positive
    CHECK (headcount IS NULL OR headcount >= 1);

-- Verify the new columns.
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venue_bookings'
ORDER BY ordinal_position;
