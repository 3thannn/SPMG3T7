BEGIN;

DO $$ BEGIN
    CREATE TYPE public.unavailability_reason_type AS ENUM (
        'maintenance', 'equipment_failure', 'renovation', 'safety_concern', 'other'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE public.venue_unavailability
    ADD COLUMN IF NOT EXISTS reason_type public.unavailability_reason_type,
    ADD COLUMN IF NOT EXISTS other_reason TEXT;

UPDATE public.venue_unavailability
SET reason_type = 'other', other_reason = COALESCE(NULLIF(btrim(reason), ''), 'Venue unavailable')
WHERE reason_type IS NULL OR (reason_type = 'other' AND NULLIF(btrim(other_reason), '') IS NULL);

ALTER TABLE public.venue_unavailability
    ALTER COLUMN reason_type SET DEFAULT 'other',
    ALTER COLUMN reason_type SET NOT NULL,
    DROP CONSTRAINT IF EXISTS venue_unavailability_other_reason_check;
ALTER TABLE public.venue_unavailability
    ADD CONSTRAINT venue_unavailability_other_reason_check CHECK (
        (reason_type <> 'other' AND other_reason IS NULL) OR
        (reason_type = 'other' AND NULLIF(btrim(other_reason), '') IS NOT NULL)
    );

ALTER TYPE public.booking_status ADD VALUE IF NOT EXISTS 'Needs replacement';
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS replacement_reason TEXT,
    ADD COLUMN IF NOT EXISTS flagged_by_unavailability_id INTEGER
        REFERENCES public.venue_unavailability(id) ON DELETE SET NULL;

-- Every story's exception in one definition, as SUPABASE_FIX_DECISION_RECORDED.sql
-- has it. This used to leave out US4.6's, so re-running this script broke
-- cancelling an event with a Confirmed booking.
ALTER TABLE public.venue_bookings DROP CONSTRAINT IF EXISTS venue_bookings_decision_recorded;
ALTER TABLE public.venue_bookings ADD CONSTRAINT venue_bookings_decision_recorded CHECK (
    CASE
        WHEN status::text IN ('Confirmed', 'Rejected') THEN decided_at IS NOT NULL
        WHEN status::text IN ('Cancelled', 'Needs replacement', 'Replaced') THEN TRUE
        ELSE decided_at IS NULL
    END
);

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

CREATE INDEX IF NOT EXISTS ix_venue_bookings_flagged_by_unavailability
    ON public.venue_bookings (flagged_by_unavailability_id)
    WHERE flagged_by_unavailability_id IS NOT NULL;

COMMIT;
NOTIFY pgrst, 'reload schema';
