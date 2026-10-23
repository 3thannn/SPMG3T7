-- US20.2: an Attendee sees their registrations and withdraws before the event
-- starts, giving the place back.
-- Apply once to an existing Supabase project, after
-- SUPABASE_US20_1_REGISTRATION.sql, and before deploying the withdraw route.
-- Safe to run repeatedly: every statement is IF NOT EXISTS, CREATE OR REPLACE,
-- or drops what it re-adds.
--
-- Without it, "My Registrations" and withdrawing return 500; registering and
-- every other route are unaffected.
--
-- Registering again after withdrawing needs nothing here. US20.1 counts only
-- Registered rows, for the capacity and for one-per-Attendee alike, so a
-- withdrawn row is history and a new registration is a new row.
--
-- The new enum value is only compared as text below (`status::text`), never
-- used as an enum literal, because Postgres refuses a value added in the same
-- transaction that uses it, and the SQL Editor runs a script as one.

-- 1. The status, and when it happened. Naive UTC, like every recorded time.
ALTER TYPE public.registration_status ADD VALUE IF NOT EXISTS 'Withdrawn';

ALTER TABLE public.registrations
    ADD COLUMN IF NOT EXISTS withdrawn_at TIMESTAMP;
ALTER TABLE public.registrations
    DROP CONSTRAINT IF EXISTS registrations_withdrawal_recorded;
ALTER TABLE public.registrations
    ADD CONSTRAINT registrations_withdrawal_recorded CHECK (
        (status::text = 'Withdrawn') = (withdrawn_at IS NOT NULL)
    );

-- 2. Withdrawing. Returns {"outcome": ...}:
--      withdrawn          plus "withdrawnAt"
--      not-found          no such registration, or not this Attendee's
--      already-withdrawn  it was withdrawn before
--      closed             the event is no longer Confirmed
--      started            the event's start has passed (Singapore time, like
--                         the event times): too late to give the place back
--    The event is locked before the registration, the order register_for_event
--    and the capacity trigger take them in, so a withdrawal and a registration
--    for the same event queue rather than deadlock. Once committed, the place
--    counts as free: US20.1's count is of Registered rows.
CREATE OR REPLACE FUNCTION public.withdraw_registration(
    p_registration_id INTEGER, p_attendee_id INTEGER
) RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    reg_event INTEGER;
    reg_attendee INTEGER;
    reg_status TEXT;
    event_status TEXT;
    event_start TIMESTAMP;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
    local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Singapore';
BEGIN
    SELECT event_id, attendee_id INTO reg_event, reg_attendee
    FROM public.registrations WHERE id = p_registration_id;
    IF NOT FOUND OR reg_attendee IS DISTINCT FROM p_attendee_id THEN
        RETURN jsonb_build_object('outcome', 'not-found');
    END IF;
    SELECT status::text, proposed_date INTO event_status, event_start
    FROM public.events WHERE id = reg_event FOR UPDATE;
    SELECT status::text INTO reg_status
    FROM public.registrations WHERE id = p_registration_id FOR UPDATE;

    IF reg_status <> 'Registered' THEN
        RETURN jsonb_build_object('outcome', 'already-withdrawn');
    END IF;
    IF event_status IS DISTINCT FROM 'Confirmed' THEN
        RETURN jsonb_build_object('outcome', 'closed');
    END IF;
    IF event_start IS NOT NULL AND event_start <= local_now THEN
        RETURN jsonb_build_object('outcome', 'started');
    END IF;

    UPDATE public.registrations
    SET status = 'Withdrawn', withdrawn_at = changed_at
    WHERE id = p_registration_id;
    RETURN jsonb_build_object(
        'outcome', 'withdrawn',
        'withdrawnAt', to_char(changed_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    );
END;
$$;
REVOKE ALL ON FUNCTION public.withdraw_registration(INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.withdraw_registration(INTEGER, INTEGER)
    TO service_role;

NOTIFY pgrst, 'reload schema';

-- Verify the status, the column and the function.
SELECT enumlabel FROM pg_enum
WHERE enumtypid = 'public.registration_status'::regtype
ORDER BY enumsortorder;

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'registrations' AND column_name = 'withdrawn_at';

SELECT proname, pg_get_function_arguments(oid)
FROM pg_proc
WHERE proname = 'withdraw_registration' AND pronamespace = 'public'::regnamespace;
