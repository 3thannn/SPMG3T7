-- US14.5: request a replacement venue for a booking flagged Needs replacement.
--
-- request_replacement_venue was first created on the live database only, so a
-- database built from this repo had no such function and requesting a
-- replacement answered 500 (A3, PROJECT_AUDIT 2026-11-04). This is the
-- committed version, written to match what the API and its in-memory stand-in
-- (InMemoryBookings.request_replacement) expect:
--   * the booking must be Needs replacement, on an event that is not closed and
--     is assigned to the caller, and the new venue must exist and differ;
--   * the new venue is locked and checked under US15.1's rule (requests count);
--   * a new Requested booking copies the old one's times, headcount and needs,
--     and the old one becomes Replaced, in one transaction;
--   * returns the new booking's id, -1 when the slot is taken, or NULL when
--     any other check fails.
--
-- It is created only where it does not exist yet, so the live database keeps
-- its own version. Apply after SUPABASE_US14_5_REPLACED_STATUS.sql,
-- SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql and
-- SUPABASE_ADD_BOOKING_CONFLICTS.sql, and before
-- SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql. Safe to run repeatedly.

DO $outer$ BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_proc
        WHERE proname = 'request_replacement_venue' AND pronamespace = 'public'::regnamespace
    ) THEN
        RETURN;
    END IF;
    EXECUTE $create$
CREATE FUNCTION public.request_replacement_venue(
    p_booking_id INTEGER, p_venue_id INTEGER, p_actor_id INTEGER
) RETURNS INTEGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    old_booking RECORD;
    current_status TEXT;
    assigned_id INTEGER;
    new_id INTEGER;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.venues WHERE id = p_venue_id) THEN
        RETURN NULL;
    END IF;
    -- Venue, then booking, then event: the order every booking function takes.
    PERFORM 1 FROM public.venues WHERE id = p_venue_id FOR UPDATE;
    SELECT * INTO old_booking FROM public.venue_bookings WHERE id = p_booking_id FOR UPDATE;
    IF NOT FOUND OR old_booking.status::text <> 'Needs replacement'
        OR old_booking.venue_id = p_venue_id THEN
        RETURN NULL;
    END IF;
    SELECT status::text, coordinator_id INTO current_status, assigned_id
    FROM public.events WHERE id = old_booking.event_id FOR UPDATE;
    IF NOT FOUND OR current_status IN ('Completed', 'Cancelled', 'Rejected')
        OR assigned_id IS DISTINCT FROM p_actor_id THEN
        RETURN NULL;
    END IF;
    IF public.venue_slot_clashes(
        p_venue_id, old_booking.start_at, old_booking.end_at, NULL, TRUE
    ) THEN
        RETURN -1;
    END IF;
    INSERT INTO public.venue_bookings
        (event_id, venue_id, start_at, end_at, status, requested_by_id, created_at,
         headcount, required_layout, required_facilities, accessibility_needs)
    VALUES
        (old_booking.event_id, p_venue_id, old_booking.start_at, old_booking.end_at,
         'Requested', p_actor_id, timezone('UTC', clock_timestamp()),
         old_booking.headcount, old_booking.required_layout,
         old_booking.required_facilities, old_booking.accessibility_needs)
    RETURNING id INTO new_id;
    UPDATE public.venue_bookings SET status = 'Replaced' WHERE id = p_booking_id;
    RETURN new_id;
END;
$$
    $create$;
    REVOKE ALL ON FUNCTION public.request_replacement_venue(INTEGER, INTEGER, INTEGER)
        FROM PUBLIC, anon, authenticated;
    GRANT EXECUTE ON FUNCTION public.request_replacement_venue(INTEGER, INTEGER, INTEGER)
        TO service_role;
END $outer$;

NOTIFY pgrst, 'reload schema';
