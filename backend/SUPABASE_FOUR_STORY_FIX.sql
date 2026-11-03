-- Run this entire file in Supabase SQL Editor for the audited demo project.
-- Preserves existing bookings and notices; adds missing notices for current coordinators.

-- US14.5: Add 'Replaced' status to booking_status enum for replacement bookings
-- A booking marked 'Replaced' is kept for history but no longer holds its venue.

-- Add the new status value
ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'Replaced';

-- Document that 'Replaced' is a terminal status like 'Cancelled' and 'Rejected'
-- and that replaced bookings are kept in the database for audit trail purposes.
BEGIN;

DO $$
DECLARE definition TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO definition
    FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass
      AND conname = 'notifications_kind_valid';
    IF definition IS NOT NULL THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7)
            || ') OR (kind IN (''assigned'', ''unassigned'', ''booking-conflict'')'
            || ' AND status IS NULL AND equipment_request_id IS NULL))';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.reassign_event_coordinator(
    p_event_id INTEGER, p_coordinator_id INTEGER, p_assigned_by_id INTEGER,
    p_expected_updated_at TIMESTAMP
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    current_event public.events%ROWTYPE;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = p_assigned_by_id
                   AND role = 'Event Coordinator Lead')
       OR NOT EXISTS (SELECT 1 FROM public.users WHERE id = p_coordinator_id
                      AND role = 'Event Coordinator') THEN
        RETURN FALSE;
    END IF;
    SELECT * INTO current_event FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_event.coordinator_id IS NULL
        OR current_event.updated_at IS DISTINCT FROM p_expected_updated_at THEN
        RETURN FALSE;
    END IF;
    IF current_event.coordinator_id = p_coordinator_id THEN RETURN TRUE; END IF;

    UPDATE public.events SET coordinator_id = p_coordinator_id, updated_at = changed_at
    WHERE id = p_event_id;

    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at, notes)
    VALUES (p_event_id, current_event.status, current_event.status,
        p_assigned_by_id, changed_at,
        format('Coordinator reassigned from %s to %s.',
               current_event.coordinator_id, p_coordinator_id));

    INSERT INTO public.notifications (user_id, event_id, kind, status, message)
    VALUES
        (current_event.coordinator_id, p_event_id, 'unassigned', NULL,
         format('"%s" is no longer assigned to you.', current_event.name)),
        (p_coordinator_id, p_event_id, 'assigned', NULL,
         format('You were assigned "%s".', current_event.name));

    IF EXISTS (SELECT 1 FROM public.venue_bookings
               WHERE event_id = p_event_id AND status::text = 'Needs replacement') THEN
        INSERT INTO public.notifications (user_id, event_id, kind, status, message)
        VALUES (p_coordinator_id, p_event_id, 'booking-conflict', NULL,
                format('"%s" has venue bookings that need replacement. Review its bookings.',
                       current_event.name));
    END IF;
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.reassign_event_coordinator(INTEGER, INTEGER, INTEGER, TIMESTAMP)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reassign_event_coordinator(INTEGER, INTEGER, INTEGER, TIMESTAMP)
    TO service_role;

INSERT INTO public.notifications (user_id, event_id, kind, status, message)
SELECT event.coordinator_id, event.id, 'booking-conflict', NULL,
       format('"%s" has venue bookings that need replacement. Review its bookings.', event.name)
FROM public.events event
WHERE event.coordinator_id IS NOT NULL
  AND event.status::text NOT IN ('Completed', 'Cancelled', 'Rejected')
  AND EXISTS (SELECT 1 FROM public.venue_bookings booking
              WHERE booking.event_id = event.id AND booking.status::text = 'Needs replacement')
  AND NOT EXISTS (SELECT 1 FROM public.notifications notice
                  WHERE notice.event_id = event.id AND notice.user_id = event.coordinator_id
                    AND notice.kind = 'booking-conflict');

NOTIFY pgrst, 'reload schema';
COMMIT;
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

ALTER TABLE public.venue_bookings DROP CONSTRAINT IF EXISTS venue_bookings_decision_recorded;
ALTER TABLE public.venue_bookings ADD CONSTRAINT venue_bookings_decision_recorded CHECK (
    status::text IN ('Needs replacement', 'Replaced', 'Cancelled')
    OR ((status::text IN ('Confirmed', 'Rejected')) = (decided_at IS NOT NULL))
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
                  AND booking.hold_expires_at > timezone('Asia/Singapore', now()))
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
-- Apply after SUPABASE_US14_5_REPLACED_STATUS.sql and SUPABASE_ADD_BOOKING_CONFLICTS.sql.
BEGIN;

ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_decision_recorded;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_decision_recorded CHECK (
        status::text IN ('Needs replacement', 'Replaced', 'Cancelled')
        OR ((status::text IN ('Confirmed', 'Rejected')) = (decided_at IS NOT NULL))
    );

CREATE OR REPLACE FUNCTION public.request_replacement_venue(
    p_booking_id INTEGER, p_venue_id INTEGER, p_actor_id INTEGER
) RETURNS INTEGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    original public.venue_bookings%ROWTYPE;
    current_event public.events%ROWTYPE;
    replacement_id INTEGER;
BEGIN
    PERFORM 1 FROM public.venues WHERE id = p_venue_id FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;

    SELECT * INTO original FROM public.venue_bookings
    WHERE id = p_booking_id FOR UPDATE;
    IF NOT FOUND OR original.status::text <> 'Needs replacement'
        OR original.venue_id = p_venue_id THEN
        RETURN NULL;
    END IF;

    SELECT * INTO current_event FROM public.events
    WHERE id = original.event_id FOR UPDATE;
    IF NOT FOUND OR current_event.coordinator_id IS DISTINCT FROM p_actor_id
        OR current_event.status::text IN ('Rejected', 'Cancelled', 'Completed') THEN
        RETURN NULL;
    END IF;

    IF public.venue_slot_clashes(
        p_venue_id, original.start_at, original.end_at, NULL, TRUE
    ) THEN
        RETURN -1;
    END IF;

    INSERT INTO public.venue_bookings (
        event_id, venue_id, start_at, end_at, status, requested_by_id,
        created_at, headcount, required_layout, required_facilities, accessibility_needs
    ) VALUES (
        original.event_id, p_venue_id, original.start_at, original.end_at,
        'Requested', p_actor_id, timezone('UTC', clock_timestamp()),
        original.headcount, original.required_layout, original.required_facilities,
        original.accessibility_needs
    ) RETURNING id INTO replacement_id;

    UPDATE public.venue_bookings SET status = 'Replaced' WHERE id = p_booking_id;
    RETURN replacement_id;
END;
$$;

REVOKE ALL ON FUNCTION public.request_replacement_venue(INTEGER, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.request_replacement_venue(INTEGER, INTEGER, INTEGER)
    TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;

