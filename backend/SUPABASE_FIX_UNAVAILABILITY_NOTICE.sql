-- Fix: marking a venue unavailable fails when it overlaps a booking, with
--   new row for relation "notifications" violates check constraint
--   "notifications_kind_valid"
-- (the browser reports it as a CORS error, because the API answers 500).
--
-- Cause. The live database's flag_bookings_for_unavailability() writes the
-- event's status onto its 'booking-conflict' notice. Every committed version
-- of SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql writes NULL, which is what
-- notifications_kind_valid requires for every kind but 'event-status', so the
-- function on the database was changed outside the repo.
--
-- This puts back the committed function, exactly as US12.2 defines it, and
-- nothing else. It does not re-run the US12.2 script, whose
-- venue_bookings_decision_recorded definition predates
-- SUPABASE_FIX_DECISION_RECORDED.sql.
--
-- Safe to run more than once.

-- Optional, before: what is installed now.
--   SELECT pg_get_functiondef('public.flag_bookings_for_unavailability'::regproc);

CREATE OR REPLACE FUNCTION public.flag_bookings_for_unavailability()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    affected_booking RECORD;
    notified_events INTEGER[] := ARRAY[]::INTEGER[];
    reason_text TEXT;
BEGIN
    reason_text := CASE NEW.reason_type
        WHEN 'maintenance' THEN 'scheduled maintenance'
        WHEN 'equipment_failure' THEN 'equipment failure'
        WHEN 'renovation' THEN 'renovation work'
        WHEN 'safety_concern' THEN 'safety concern'
        ELSE NEW.other_reason
    END;

    FOR affected_booking IN
        SELECT booking.id, booking.event_id, venue.name AS venue_name,
               event.coordinator_id, event.name AS event_name
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

        IF affected_booking.coordinator_id IS NOT NULL
           AND NOT (affected_booking.event_id = ANY(notified_events)) THEN
            INSERT INTO public.notifications (user_id, event_id, kind, status, message)
            VALUES (
                affected_booking.coordinator_id, affected_booking.event_id,
                'booking-conflict', NULL,
                format(
                    'The booking of %s for "%s" needs attention: the venue is unavailable %s–%s due to %s.',
                    affected_booking.venue_name, affected_booking.event_name,
                    to_char(NEW.start_date, 'DD Mon YYYY'),
                    to_char(NEW.end_date, 'DD Mon YYYY'), reason_text
                )
            );
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
