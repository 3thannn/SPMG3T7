-- US14.3: Venue Staff place a tentative hold on a venue with an expiry, so a
-- slot is kept for a Coordinator who is still finalising without blocking the
-- venue forever.
-- Apply once to an existing Supabase project, after
-- SUPABASE_CANCEL_VENUE_BOOKINGS.sql, SUPABASE_ADD_BOOKING_NEEDS.sql and
-- SUPABASE_US4_5_LIFECYCLE.sql, and before deploying the /holds routes and
-- POST /events/{id}/bookings/{bookingId}/request. Safe to run repeatedly: every
-- statement is IF NOT EXISTS or otherwise idempotent.
--
-- A hold is a venue booking with status Held, linked to its event and so to
-- the event's Coordinator. It holds the venue only until hold_expires_at. Nothing
-- rewrites an expired hold: it stays Held and simply stops counting, so no
-- scheduled job is needed for the slot to free up.

ALTER TYPE public.booking_status ADD VALUE IF NOT EXISTS 'Held';

-- When the hold lapses: a naive Singapore local time, like start_at and end_at.
-- Kept after the hold becomes a request, as the record of how it started.
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS hold_expires_at TIMESTAMP;
-- Who placed it. SET NULL so removing a user keeps the hold. Named explicitly:
-- this is the table's third foreign key to users, so PostgREST needs the
-- constraint name to embed it.
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS held_by_id INTEGER;
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_held_by_id_fkey;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_held_by_id_fkey
    FOREIGN KEY (held_by_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- A Held booking always has an expiry: a hold must never block a venue for
-- longer than anyone agreed to. `status::text` rather than the enum literal,
-- because Postgres will not let a value added above be used before this
-- script commits.
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_hold_has_expiry;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_hold_has_expiry CHECK (
        status::text <> 'Held' OR hold_expires_at IS NOT NULL
    );

CREATE INDEX IF NOT EXISTS ix_venue_bookings_held_by_id
    ON public.venue_bookings (held_by_id);

-- US14.3 with US4.5: the Coordinator turns a hold into a request. Held ->
-- Requested, and an Approved event moves to Planning, in one transaction, as
-- request_venue_and_plan does for a new request. Re-checks under row locks
-- what the API already checked, and says which check failed:
--   'requested'    done
--   'not-held'     the booking is gone, or no longer Held (requested or cancelled)
--   'expired'      the hold lapsed; compared in Singapore time, like the times
--   'stale-event'  the event moved on, or is no longer this Coordinator's
CREATE OR REPLACE FUNCTION public.request_held_booking(
    p_booking_id INTEGER, p_expected_status public.event_status,
    p_requested_by_id INTEGER
) RETURNS TEXT LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    held_event_id INTEGER;
    held_status TEXT;
    expires_at TIMESTAMP;
    current_status public.event_status;
    assigned_id INTEGER;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    SELECT event_id, status::text, hold_expires_at
    INTO held_event_id, held_status, expires_at
    FROM public.venue_bookings WHERE id = p_booking_id FOR UPDATE;
    IF NOT FOUND OR held_status <> 'Held' THEN
        RETURN 'not-held';
    END IF;
    IF expires_at <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore') THEN
        RETURN 'expired';
    END IF;
    SELECT status, coordinator_id INTO current_status, assigned_id
    FROM public.events WHERE id = held_event_id FOR UPDATE;
    IF NOT FOUND OR current_status <> p_expected_status
        OR current_status NOT IN ('Approved', 'Planning')
        OR assigned_id IS DISTINCT FROM p_requested_by_id THEN
        RETURN 'stale-event';
    END IF;
    UPDATE public.venue_bookings
    SET status = 'Requested', requested_by_id = p_requested_by_id
    WHERE id = p_booking_id;
    IF current_status = 'Approved' THEN
        UPDATE public.events SET status = 'Planning', updated_at = changed_at
        WHERE id = held_event_id;
        INSERT INTO public.status_changes
            (event_id, old_status, new_status, changed_by_id, changed_at)
        VALUES (held_event_id, 'Approved', 'Planning', p_requested_by_id, changed_at);
    END IF;
    RETURN 'requested';
END;
$$;
REVOKE ALL ON FUNCTION public.request_held_booking(INTEGER, public.event_status, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.request_held_booking(INTEGER, public.event_status, INTEGER)
    TO service_role;

NOTIFY pgrst, 'reload schema';

-- Verify the new columns and the enum value.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venue_bookings'
  AND column_name IN ('hold_expires_at', 'held_by_id');

SELECT enumlabel
FROM pg_enum
WHERE enumtypid = 'public.booking_status'::regtype
ORDER BY enumsortorder;
