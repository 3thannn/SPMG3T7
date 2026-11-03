-- US10.4: registered Attendees are told when their event's date, time or venue
-- changes. Apply once to an existing Supabase project, after
-- SUPABASE_US4_7_CONFIRM_EVENT.sql, and before deploying the US10.4 code.
-- Safe to run repeatedly: it checks before it changes anything.
--
-- Without it, those notices are rejected by notifications_kind_valid, so
-- Attendees are not told. Approving the change or the replacement venue still
-- succeeds; the failure is only logged.

BEGIN;

-- The Attendee's notice. Added to whatever notifications_kind_valid holds now,
-- so no other story's kinds are lost.
DO $$ DECLARE definition TEXT; BEGIN
    SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass AND conname = 'notifications_kind_valid';
    IF definition NOT LIKE '%event-updated%' THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7) || ') OR (kind = ''event-updated'''
            || ' AND status IS NULL AND equipment_request_id IS NULL))';
    END IF;
END $$;

COMMIT;

-- Verify the notice kind.
SELECT pg_get_constraintdef(oid) LIKE '%event-updated%' AS has_notice_kind
FROM pg_constraint WHERE conname = 'notifications_kind_valid';
