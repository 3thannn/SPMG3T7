-- US9.5: a venue with no future bookings can be deleted, history and all.
--
-- Until now `venue_bookings.venue_id` had no ON DELETE action, so any booking
-- at all, even one cancelled years ago, stopped a venue being deleted. The team
-- chose to let those go: deleting a venue now deletes its bookings with it.
-- That removes the past and closed bookings from their events' history; the
-- events themselves and their status changes are untouched.
--
-- A booking still to come must never go that way, so a trigger refuses the
-- delete while the venue has one. The API checks first and gives the reason;
-- the trigger is what makes it safe when a booking lands between that check
-- and the delete. "Still to come" matches `Booking.upcoming_at` and
-- `Booking.awaiting_replacement_at` in app/booking_store.py: not yet ended, and
-- Requested, Confirmed, Needs replacement, or Held with the hold not lapsed.
--
-- Run after the US14.3 (hold_expires_at) and US12.2 (Needs replacement)
-- scripts. Idempotent: running it twice is a no-op.

BEGIN;

-- 1. A venue's bookings go with it. The constraint is found by what it links
--    rather than by name, in case a project's was named differently.
DO $$
DECLARE
    fk_name TEXT;
BEGIN
    FOR fk_name IN
        SELECT con.conname
        FROM pg_constraint AS con
        WHERE con.conrelid = 'public.venue_bookings'::regclass
          AND con.confrelid = 'public.venues'::regclass
          AND con.contype = 'f'
    LOOP
        EXECUTE format('ALTER TABLE public.venue_bookings DROP CONSTRAINT %I', fk_name);
    END LOOP;
END $$;

ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_venue_id_fkey
    FOREIGN KEY (venue_id) REFERENCES public.venues(id) ON DELETE CASCADE;

-- 2. ...but never while one of them is still to come. SQLSTATE VB905 is this
--    refusal's own, so the API can tell it from any other failure.
CREATE OR REPLACE FUNCTION public.refuse_deleting_booked_venue()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    -- Booking times are naive Singapore local time, as in the other scripts.
    local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Singapore';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.venue_bookings AS booking
        WHERE booking.venue_id = OLD.id
          AND booking.end_at > local_now
          AND (
              booking.status IN ('Requested', 'Confirmed', 'Needs replacement')
              OR (booking.status = 'Held' AND booking.hold_expires_at > local_now)
          )
    ) THEN
        RAISE EXCEPTION 'Venue % has future bookings', OLD.id
            USING ERRCODE = 'VB905';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS venues_refuse_delete_while_booked ON public.venues;
CREATE TRIGGER venues_refuse_delete_while_booked
    BEFORE DELETE ON public.venues
    FOR EACH ROW
    EXECUTE FUNCTION public.refuse_deleting_booked_venue();

COMMIT;
