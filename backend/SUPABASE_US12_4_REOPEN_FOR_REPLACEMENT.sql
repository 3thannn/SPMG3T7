-- US12.4: a venue problem on a Confirmed event reopens planning.
-- Apply once to an existing Supabase project, after
-- SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql (or
-- SUPABASE_FIX_UNAVAILABILITY_NOTICE.sql), SUPABASE_US14_5_REPLACED_STATUS.sql
-- and SUPABASE_US11_3_RECONFIRM.sql, and before deploying the US12.4 code.
-- Safe to run repeatedly: every statement is CREATE OR REPLACE or drops what it
-- re-adds.
--
-- Without it, requesting a replacement venue returns 500, because the API now
-- requests it through us12_4_request_replacement. Searching for one, and every
-- other route, is unaffected.
--
-- request_replacement_venue (US14.5) is left as it is and called from the new
-- function, rather than copied into it: it is not in the repo, so the live
-- one keeps whatever it does, as US11.3 did with us11_review.

BEGIN;

-- 1. US12.2's flagging, as SUPABASE_FIX_UNAVAILABILITY_NOTICE.sql defines it,
--    with one addition: on a Confirmed event the Organiser is told as well,
--    once per event. The event's status is not touched; the customer said the
--    system must not move it on its own. Both notices are 'booking-conflict',
--    which notifications_kind_valid already allows with no status.
CREATE OR REPLACE FUNCTION public.flag_bookings_for_unavailability()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    affected_booking RECORD;
    notified_events INTEGER[] := ARRAY[]::INTEGER[];
    reason_text TEXT;
    dates_text TEXT;
BEGIN
    reason_text := CASE NEW.reason_type
        WHEN 'maintenance' THEN 'scheduled maintenance'
        WHEN 'equipment_failure' THEN 'equipment failure'
        WHEN 'renovation' THEN 'renovation work'
        WHEN 'safety_concern' THEN 'safety concern'
        ELSE NEW.other_reason
    END;
    dates_text := to_char(NEW.start_date, 'DD Mon YYYY') || '–'
        || to_char(NEW.end_date, 'DD Mon YYYY');

    FOR affected_booking IN
        SELECT booking.id, booking.event_id, venue.name AS venue_name,
               event.coordinator_id, event.organiser_id, event.name AS event_name,
               event.status::text AS event_status
        FROM public.venue_bookings AS booking
        JOIN public.venues AS venue ON venue.id = booking.venue_id
        JOIN public.events AS event ON event.id = booking.event_id
        WHERE booking.venue_id = NEW.venue_id
          AND (
              booking.status::text IN ('Requested', 'Confirmed')
              OR (booking.status::text = 'Held'
                  AND booking.hold_expires_at > timezone('UTC', now()))
          )
          AND booking.start_at - make_interval(mins => venue.setup_minutes)
              < NEW.end_date::timestamp + INTERVAL '1 day'
          AND NEW.start_date::timestamp
              < booking.end_at + make_interval(mins => venue.turnaround_minutes)
        ORDER BY booking.id
        FOR UPDATE OF booking
    LOOP
        UPDATE public.venue_bookings
        SET status = 'Needs replacement', replacement_reason = reason_text,
            flagged_by_unavailability_id = NEW.id
        WHERE id = affected_booking.id;

        IF NOT (affected_booking.event_id = ANY(notified_events)) THEN
            IF affected_booking.coordinator_id IS NOT NULL THEN
                INSERT INTO public.notifications (user_id, event_id, kind, status, message)
                VALUES (
                    affected_booking.coordinator_id, affected_booking.event_id,
                    'booking-conflict', NULL,
                    format(
                        'The booking of %s for "%s" needs attention: the venue is unavailable %s due to %s.',
                        affected_booking.venue_name, affected_booking.event_name,
                        dates_text, reason_text
                    )
                );
            END IF;
            -- US12.4: the Organiser of a Confirmed event hears too. Not twice,
            -- should they also be its Coordinator.
            IF affected_booking.event_status = 'Confirmed'
               AND affected_booking.organiser_id IS DISTINCT FROM affected_booking.coordinator_id THEN
                INSERT INTO public.notifications (user_id, event_id, kind, status, message)
                VALUES (
                    affected_booking.organiser_id, affected_booking.event_id,
                    'booking-conflict', NULL,
                    format(
                        'A venue for "%s" is affected: %s is unavailable %s due to %s. '
                        'Your Coordinator will arrange a replacement, and the event goes '
                        'back to Planning when they do.',
                        affected_booking.event_name, affected_booking.venue_name,
                        dates_text, reason_text
                    )
                );
            END IF;
            notified_events := array_append(notified_events, affected_booking.event_id);
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trigger_flag_bookings_on_unavailability ON public.venue_unavailability;
CREATE TRIGGER trigger_flag_bookings_on_unavailability
    AFTER INSERT ON public.venue_unavailability
    FOR EACH ROW EXECUTE FUNCTION public.flag_bookings_for_unavailability();

-- 2. Request a replacement venue. request_replacement_venue does it, exactly as
--    before; then, if that replaced a booking that Needed replacement on an
--    event that was Confirmed, the event moves back to Planning with a
--    status_changes entry carrying p_reason. One transaction, so the
--    replacement never lands without the move. The event's other bookings are
--    not touched. Returns what request_replacement_venue returns, whatever its
--    type, as JSON, so the API reads it as it did before.
CREATE OR REPLACE FUNCTION public.us12_4_request_replacement(
    p_booking_id INTEGER,
    p_venue_id INTEGER,
    p_actor_id INTEGER,
    p_reason TEXT
) RETURNS JSONB LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_event_id INTEGER;
    v_event_status TEXT;
    v_booking_status TEXT;
    v_result JSONB;
    v_at TIMESTAMP;
BEGIN
    SELECT event_id INTO v_event_id FROM public.venue_bookings WHERE id = p_booking_id;
    SELECT status::text INTO v_event_status FROM public.events WHERE id = v_event_id FOR UPDATE;
    SELECT status::text INTO v_booking_status
    FROM public.venue_bookings WHERE id = p_booking_id FOR UPDATE;

    v_result := to_jsonb(public.request_replacement_venue(
        p_booking_id => p_booking_id, p_venue_id => p_venue_id, p_actor_id => p_actor_id
    ));

    -- Only a replacement this call made: a booking already Replaced before it
    -- (a stale retry) must not reopen an event Confirmed again since.
    IF v_event_status = 'Confirmed'
       AND v_booking_status = 'Needs replacement'
       AND EXISTS (
           SELECT 1 FROM public.venue_bookings
           WHERE id = p_booking_id AND status::text = 'Replaced'
       ) THEN
        v_at := timezone('UTC', clock_timestamp());
        UPDATE public.events
        SET status = 'Planning'::text::public.event_status, updated_at = v_at
        WHERE id = v_event_id;
        INSERT INTO public.status_changes
            (event_id, old_status, new_status, changed_by_id, changed_at, notes)
        VALUES (v_event_id, 'Confirmed', 'Planning', p_actor_id, v_at,
                NULLIF(btrim(COALESCE(p_reason, '')), ''));
    END IF;
    RETURN v_result;
END;
$$;
REVOKE ALL ON FUNCTION public.us12_4_request_replacement(INTEGER, INTEGER, INTEGER, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.us12_4_request_replacement(INTEGER, INTEGER, INTEGER, TEXT)
    TO service_role;

NOTIFY pgrst, 'reload schema';

COMMIT;

-- Verify the trigger function and the new function.
SELECT pg_get_functiondef('public.flag_bookings_for_unavailability'::regproc)
    LIKE '%Your Coordinator will arrange a replacement%' AS organiser_is_told;

SELECT proname, pg_get_function_arguments(oid)
FROM pg_proc
WHERE proname IN ('us12_4_request_replacement', 'request_replacement_venue')
  AND pronamespace = 'public'::regnamespace;
