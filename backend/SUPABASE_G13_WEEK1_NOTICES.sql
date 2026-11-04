-- G13: the Week 1 notifications that had no story. Venue Staff are told when a
-- venue booking is requested; Attendees when an event opens for registration,
-- and those registered when it closes; the Organiser and Coordinator when an
-- Attendee withdraws and frees a place. The API writes them (app/notifications.py).
--
-- Apply once to an existing Supabase project, after
-- SUPABASE_US10_4_EVENT_UPDATED_NOTICE.sql, and before deploying the code that
-- writes them. Safe to run repeatedly: it checks before it changes anything.
--
-- Without it, those notices are rejected by notifications_kind_valid. The
-- request, the registration change or the withdrawal still succeeds; the
-- failure is only logged.

BEGIN;

-- Added to whatever notifications_kind_valid holds now, so no other story's
-- kinds are lost.
DO $$ DECLARE definition TEXT; BEGIN
    SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass AND conname = 'notifications_kind_valid';
    IF definition NOT LIKE '%booking-requested%' THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7) || ') OR (kind IN '
            || '(''booking-requested'', ''registration-opened'', ''registration-closed'', '
            || '''attendee-withdrew'')'
            || ' AND status IS NULL AND equipment_request_id IS NULL))';
    END IF;
END $$;

COMMIT;

-- Verify the notice kinds.
SELECT pg_get_constraintdef(oid) LIKE '%attendee-withdrew%' AS has_week1_notices
FROM pg_constraint WHERE conname = 'notifications_kind_valid';
