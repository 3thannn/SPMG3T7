-- US14.3 (reworked) and US14.6: a tentative hold starts after venue approval,
-- and Venue Staff can change its expiry or release it.
--
-- Week 9 clarified Week 7 change #4: tentative holding starts after Venue Staff
-- approve the venue, Venue Staff set and update how long it lasts, and the
-- Coordinator confirms once Venue Staff approve. Before this, Venue Staff placed
-- a hold first and the Coordinator turned it into a request (request_held_booking).
-- Now:
--   Requested --Venue Staff approve, with an expiry--> Held
--   Held --Coordinator confirms, before the expiry--> Confirmed
--   Held --expiry passes--> Expired (the US14.4 sweep, unchanged)
--   Held --Venue Staff release, with a reason--> Cancelled
--   Requested --Venue Staff approve outright--> Confirmed (US16.1, unchanged)
--
-- Apply once to an existing Supabase project, after SUPABASE_US14_4_HOLD_EXPIRY.sql,
-- SUPABASE_FIX_DECISION_RECORDED.sql and SUPABASE_US10_4_EVENT_UPDATED_NOTICE.sql,
-- and before deploying the code that calls these functions. Safe to run
-- repeatedly: it checks before it changes anything, or replaces what it adds.

BEGIN;

-- 1. A Held booking is now an approval, so it carries its decision; an Expired
--    one keeps it as history. A hold placed the old way has none, and is still
--    allowed. Everything else is as SUPABASE_FIX_DECISION_RECORDED.sql left it.
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_decision_recorded;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_decision_recorded CHECK (
        CASE
            WHEN status::text IN ('Confirmed', 'Rejected') THEN decided_at IS NOT NULL
            WHEN status::text IN ('Cancelled', 'Needs replacement', 'Replaced', 'Held', 'Expired')
                THEN TRUE
            ELSE decided_at IS NULL
        END
    );

-- 2. The Coordinator's three new notices. Added to whatever
--    notifications_kind_valid holds now, so no other story's kinds are lost.
DO $$ DECLARE definition TEXT; BEGIN
    SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass AND conname = 'notifications_kind_valid';
    IF definition NOT LIKE '%hold-placed%' THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7) || ') OR (kind IN '
            || '(''hold-placed'', ''hold-updated'', ''hold-released'')'
            || ' AND status IS NULL AND equipment_request_id IS NULL))';
    END IF;
END $$;

-- 3. Venue Staff approve a request as a hold. approve_venue_booking's locks and
--    clash check, then Held with the decision, who holds it and until when.
--    The expiry rule is the API's: in the future (Singapore time, like the
--    booking times) and no later than the booking starts.
--    Returns 'held', 'clash', 'bad-expiry' or 'not-requested'.
CREATE OR REPLACE FUNCTION public.approve_venue_booking_as_hold(
    p_booking_id INTEGER, p_actor_id INTEGER, p_expires_at TIMESTAMP
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
    IF p_expires_at IS NULL
        OR p_expires_at <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore')
        OR p_expires_at > booking_start THEN
        RETURN 'bad-expiry';
    END IF;
    IF public.venue_slot_clashes(
        booking_venue_id, booking_start, booking_end, p_booking_id, FALSE
    ) THEN
        RETURN 'clash';
    END IF;
    UPDATE public.venue_bookings
    SET status = 'Held',
        decided_at = timezone('UTC', clock_timestamp()),
        decided_by_id = p_actor_id,
        hold_expires_at = p_expires_at,
        held_by_id = p_actor_id,
        expiry_warned_at = NULL
    WHERE id = p_booking_id;
    RETURN 'held';
END;
$$;
REVOKE ALL ON FUNCTION public.approve_venue_booking_as_hold(INTEGER, INTEGER, TIMESTAMP)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.approve_venue_booking_as_hold(INTEGER, INTEGER, TIMESTAMP)
    TO service_role;

-- 4. The Coordinator confirms a hold. Held -> Confirmed, before it lapses, by
--    the event's assigned Coordinator, on an event that is not closed. Booking
--    then event, as request_held_booking locked them.
--      'confirmed'    done
--      'not-held'     the booking is gone, or no longer Held
--      'expired'      the hold lapsed
--      'stale-event'  the event closed, or is no longer this Coordinator's
CREATE OR REPLACE FUNCTION public.confirm_held_booking(
    p_booking_id INTEGER, p_actor_id INTEGER
) RETURNS TEXT LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    held_event_id INTEGER;
    held_status TEXT;
    expires_at TIMESTAMP;
    current_status TEXT;
    assigned_id INTEGER;
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
    SELECT status::text, coordinator_id INTO current_status, assigned_id
    FROM public.events WHERE id = held_event_id FOR UPDATE;
    IF NOT FOUND OR current_status IN ('Completed', 'Cancelled', 'Rejected')
        OR assigned_id IS DISTINCT FROM p_actor_id THEN
        RETURN 'stale-event';
    END IF;
    UPDATE public.venue_bookings SET status = 'Confirmed' WHERE id = p_booking_id;
    RETURN 'confirmed';
END;
$$;
REVOKE ALL ON FUNCTION public.confirm_held_booking(INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.confirm_held_booking(INTEGER, INTEGER) TO service_role;

-- 5. The old order is gone: nothing turns a hold into a request any more.
DROP FUNCTION IF EXISTS public.request_held_booking(INTEGER, public.event_status, INTEGER);

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Verify the functions and the notice kinds.
SELECT proname FROM pg_proc
WHERE pronamespace = 'public'::regnamespace
  AND proname IN ('approve_venue_booking_as_hold', 'confirm_held_booking', 'request_held_booking')
ORDER BY proname;

SELECT pg_get_constraintdef(oid) LIKE '%hold-released%' AS has_hold_notices
FROM pg_constraint WHERE conname = 'notifications_kind_valid';
