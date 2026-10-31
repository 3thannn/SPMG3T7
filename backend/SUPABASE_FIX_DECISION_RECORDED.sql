-- Fix: cancelling an event with a Confirmed booking fails with
--   new row for relation "venue_bookings" violates check constraint
--   "venue_bookings_decision_recorded"
--
-- Cause. Two scripts each redefine this constraint, and the later one dropped
-- the earlier one's exception:
--
-- * SUPABASE_US4_6_CANCEL_EVENT.sql let a Cancelled booking keep the Venue
--   Staff decision that confirmed it (US4.6: a cancelled Confirmed booking
--   keeps its history).
-- * SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql then redefined it from the
--   older version, adding its own exception for 'Needs replacement' but not
--   US4.6's. Since it ran, cancel_event cannot cancel a Confirmed booking.
--
-- This puts every exception in one definition:
--
-- * Confirmed and Rejected must carry their decision.
-- * Cancelled, Needs replacement and Replaced may or may not: each can be
--   reached from Confirmed (decided) or from Requested or Held (never decided),
--   and the decision is kept as history either way.
-- * Every other status (Requested, Held, Expired) has never been decided.
--
-- Safe to run more than once. Run after SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql
-- and SUPABASE_US14_5_REPLACED_STATUS.sql. Any script that redefines this
-- constraint later must start from this definition, not an older one.

ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_decision_recorded;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_decision_recorded CHECK (
        CASE
            WHEN status::text IN ('Confirmed', 'Rejected') THEN decided_at IS NOT NULL
            WHEN status::text IN ('Cancelled', 'Needs replacement', 'Replaced') THEN TRUE
            ELSE decided_at IS NULL
        END
    );

-- Verify: the definition should show the three-branch CASE above.
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'venue_bookings_decision_recorded';
