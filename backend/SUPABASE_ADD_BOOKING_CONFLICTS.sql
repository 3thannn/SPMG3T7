-- US15.1: availability is checked against the full time a venue is occupied,
-- setup and turnaround included, and against its unavailability periods.
-- US15.2: bookings that clash after a setup/turnaround change are flagged
-- 'Conflict - review needed' rather than removed.
-- Apply once to an existing Supabase project, after
-- SUPABASE_ADD_BOOKING_DECISIONS.sql (US16.1), SUPABASE_ADD_VENUE_UNAVAILABILITY.sql
-- (US12.1) and SUPABASE_US4_5_LIFECYCLE.sql, and before deploying the
-- /booking-conflicts route. Safe to run repeatedly: every statement is
-- IF NOT EXISTS or otherwise idempotent.
--
-- Every booking read selects the two new columns, so without them every
-- /events/{id}/bookings route, /booking-requests and /holds return 500.

-- US15.2: the flag sits beside the status, never replacing it. A flagged
-- booking stays Requested, Held or Confirmed; nothing is deleted or cancelled.
-- conflict_flagged_at is a naive UTC time, as cancelled_at and decided_at are.
ALTER TABLE public.venue_bookings ADD COLUMN IF NOT EXISTS conflict_flagged_at TIMESTAMP;
ALTER TABLE public.venue_bookings ADD COLUMN IF NOT EXISTS conflict_reason TEXT;

-- A flagged booking always says why. Clearing the flag clears both.
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_conflict_has_reason;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_conflict_has_reason CHECK (
        conflict_flagged_at IS NULL
        OR (conflict_reason IS NOT NULL AND btrim(conflict_reason) <> '')
    );

-- The flagged list Venue Staff review, soonest first. Partial: few rows qualify.
CREATE INDEX IF NOT EXISTS ix_venue_bookings_conflict_flagged
    ON public.venue_bookings (start_at)
    WHERE conflict_flagged_at IS NOT NULL;

-- US15.1, the rule app/availability.py applies, in SQL:
--   * each booking occupies its start minus the venue's setup time to its end
--     plus its turnaround time (US9.4). Windows are half-open: back to back
--     (one ends 12:45, the next starts 12:45) is not a clash;
--   * Confirmed bookings and Held ones whose expiry (Singapore time, like the
--     booking times) has not passed always count. Requested ones count when
--     p_counting_requests is true: a new request is blocked by them, approval
--     is not (two requests can only overlap after a race or a US15.2 change,
--     and whichever is approved first then blocks the other);
--   * a venue unavailability period (US12.1) covers its days whole, from
--     midnight on the first to midnight after the last.
-- p_exclude_id leaves a booking out of its own check. The caller holds the
-- venue's row lock, so the answer stays true until it commits.
CREATE OR REPLACE FUNCTION public.venue_slot_clashes(
    p_venue_id INTEGER, p_start_at TIMESTAMP, p_end_at TIMESTAMP,
    p_exclude_id INTEGER, p_counting_requests BOOLEAN
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    setup INTERVAL;
    turnaround INTERVAL;
    local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Singapore';
BEGIN
    SELECT make_interval(mins => setup_minutes), make_interval(mins => turnaround_minutes)
    INTO setup, turnaround
    FROM public.venues WHERE id = p_venue_id;
    IF NOT FOUND THEN
        -- No venue, no buffers, as app/availability.py treats a missing venue.
        setup := INTERVAL '0';
        turnaround := INTERVAL '0';
    END IF;
    RETURN EXISTS (
        SELECT 1 FROM public.venue_bookings other
        WHERE other.venue_id = p_venue_id
          AND other.id IS DISTINCT FROM p_exclude_id
          AND (
              other.status::text = 'Confirmed'
              OR (other.status::text = 'Held' AND other.hold_expires_at > local_now)
              OR (p_counting_requests AND other.status::text = 'Requested')
          )
          AND other.start_at - setup < p_end_at + turnaround
          AND p_start_at - setup < other.end_at + turnaround
    ) OR EXISTS (
        SELECT 1 FROM public.venue_unavailability blackout
        WHERE blackout.venue_id = p_venue_id
          AND blackout.start_date::timestamp < p_end_at + turnaround
          AND p_start_at - setup < (blackout.end_date + 1)::timestamp
    );
END;
$$;
REVOKE ALL ON FUNCTION public.venue_slot_clashes(INTEGER, TIMESTAMP, TIMESTAMP, INTEGER, BOOLEAN)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.venue_slot_clashes(INTEGER, TIMESTAMP, TIMESTAMP, INTEGER, BOOLEAN)
    TO service_role;

-- US14.1/US4.5's request, now refused when the slot is not free (US15.1).
-- Same signature and results as before, plus -1 for a taken slot (ids are
-- SERIAL, so never negative). The venue is locked first, then the event:
-- approve_venue_booking takes venue then booking, and request_held_booking
-- booking then event, so every function takes its locks in one order
-- (venue, booking, event) and none can deadlock another.
CREATE OR REPLACE FUNCTION public.request_venue_and_plan(
    p_event_id INTEGER, p_expected_status public.event_status,
    p_venue_id INTEGER, p_start_at TIMESTAMP, p_end_at TIMESTAMP,
    p_requested_by_id INTEGER, p_headcount INTEGER,
    p_required_layout TEXT, p_required_facilities TEXT[],
    p_accessibility_needs TEXT[]
) RETURNS INTEGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    current_status public.event_status;
    assigned_id INTEGER;
    booking_id INTEGER;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    PERFORM 1 FROM public.venues WHERE id = p_venue_id FOR UPDATE;
    SELECT status, coordinator_id INTO current_status, assigned_id
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_status <> p_expected_status
        OR current_status NOT IN ('Approved', 'Planning')
        OR assigned_id IS DISTINCT FROM p_requested_by_id THEN
        RETURN NULL;
    END IF;
    IF public.venue_slot_clashes(p_venue_id, p_start_at, p_end_at, NULL, TRUE) THEN
        RETURN -1;
    END IF;
    INSERT INTO public.venue_bookings
        (event_id, venue_id, start_at, end_at, status, requested_by_id,
         created_at, headcount, required_layout, required_facilities,
         accessibility_needs)
    VALUES
        (p_event_id, p_venue_id, p_start_at, p_end_at, 'Requested',
         p_requested_by_id, changed_at, p_headcount, p_required_layout,
         p_required_facilities, p_accessibility_needs)
    RETURNING id INTO booking_id;
    IF current_status = 'Approved' THEN
        UPDATE public.events SET status = 'Planning', updated_at = changed_at
        WHERE id = p_event_id;
        INSERT INTO public.status_changes
            (event_id, old_status, new_status, changed_by_id, changed_at)
        VALUES (p_event_id, 'Approved', 'Planning', p_requested_by_id, changed_at);
    END IF;
    RETURN booking_id;
END;
$$;
REVOKE ALL ON FUNCTION public.request_venue_and_plan(
    INTEGER, public.event_status, INTEGER, TIMESTAMP, TIMESTAMP, INTEGER,
    INTEGER, TEXT, TEXT[], TEXT[]
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.request_venue_and_plan(
    INTEGER, public.event_status, INTEGER, TIMESTAMP, TIMESTAMP, INTEGER,
    INTEGER, TEXT, TEXT[], TEXT[]
) TO service_role;

-- US16.1's approval, now also blocked by a venue unavailability period
-- (US15.1). Otherwise unchanged: venue lock first, then the booking, and only
-- Confirmed and unexpired Held bookings block it. Returns 'confirmed',
-- 'clash', or 'not-requested'.
CREATE OR REPLACE FUNCTION public.approve_venue_booking(
    p_booking_id INTEGER, p_actor_id INTEGER
) RETURNS TEXT LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    booking_venue_id INTEGER;
    booking_start TIMESTAMP;
    booking_end TIMESTAMP;
    booking_status TEXT;
BEGIN
    SELECT venue_id INTO booking_venue_id
    FROM public.venue_bookings WHERE id = p_booking_id;
    IF NOT FOUND THEN
        RETURN 'not-requested';
    END IF;
    PERFORM 1 FROM public.venues WHERE id = booking_venue_id FOR UPDATE;
    SELECT start_at, end_at, status::text
    INTO booking_start, booking_end, booking_status
    FROM public.venue_bookings WHERE id = p_booking_id FOR UPDATE;
    IF booking_status <> 'Requested' THEN
        RETURN 'not-requested';
    END IF;
    IF public.venue_slot_clashes(
        booking_venue_id, booking_start, booking_end, p_booking_id, FALSE
    ) THEN
        RETURN 'clash';
    END IF;
    UPDATE public.venue_bookings
    SET status = 'Confirmed',
        decided_at = timezone('UTC', clock_timestamp()),
        decided_by_id = p_actor_id
    WHERE id = p_booking_id;
    RETURN 'confirmed';
END;
$$;
REVOKE ALL ON FUNCTION public.approve_venue_booking(INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.approve_venue_booking(INTEGER, INTEGER) TO service_role;

NOTIFY pgrst, 'reload schema';

-- Verify the new columns.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venue_bookings'
  AND column_name IN ('conflict_flagged_at', 'conflict_reason');

-- Verify the customer's worked example against the rule, without writing
-- anything: 10:00-12:00 with 30 minutes' setup and 45 minutes' turnaround
-- occupies 09:30-12:45, so a booking ending 09:30 or starting 12:45 touches it
-- and does not clash, and one ending 09:31 does.
SELECT
    (TIMESTAMP '2030-01-01 09:30' < TIMESTAMP '2030-01-01 12:00' + INTERVAL '45 minutes'
     AND TIMESTAMP '2030-01-01 10:00' - INTERVAL '30 minutes' < TIMESTAMP '2030-01-01 09:30')
        AS back_to_back_clashes,  -- expect false
    (TIMESTAMP '2030-01-01 09:00' < TIMESTAMP '2030-01-01 12:00' + INTERVAL '45 minutes'
     AND TIMESTAMP '2030-01-01 10:00' - INTERVAL '30 minutes' < TIMESTAMP '2030-01-01 09:31')
        AS one_minute_over_clashes;  -- expect true
