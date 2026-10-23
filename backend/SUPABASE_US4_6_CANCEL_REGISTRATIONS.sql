-- US4.6, the part that waited for registrations (US20.1): cancelling an event
-- marks its registrations Event Cancelled and closes its registration.
-- Apply once to an existing Supabase project, after
-- SUPABASE_US4_6_CANCEL_EVENT.sql and SUPABASE_US20_2_WITHDRAW.sql, and before
-- deploying the code that reads the new status. Safe to run repeatedly: every
-- statement is IF NOT EXISTS or CREATE OR REPLACE.
--
-- Without it, cancelling still works exactly as before; registrations stay
-- Registered on the cancelled event and registered Attendees are not told.
--
-- The new enum value is only compared as text below (`status::text`), and the
-- assignment inside cancel_event runs only when the function is called, never
-- in this script: Postgres refuses a value added in the same transaction that
-- uses it, and the SQL Editor runs a script as one.

-- 1. The status. Final: nothing moves a registration on from it.
ALTER TYPE public.registration_status ADD VALUE IF NOT EXISTS 'Event Cancelled';

-- 2. cancel_event, as SUPABASE_US4_6_CANCEL_EVENT.sql has it, and then:
--      * every Registered registration -> Event Cancelled. Withdrawn ones are
--        history and keep their status;
--      * registration closes (registration_open = false; the capacity is kept);
--      * the ids it moved are returned as "registrations", beside "bookings"
--        and "equipment", for the API to tell those Attendees.
--    Registrations are written after the event lock, the order
--    register_for_event and withdraw_registration take them in, so none of the
--    three can deadlock against another.
CREATE OR REPLACE FUNCTION public.cancel_event(
    p_event_id INTEGER, p_expected_status TEXT, p_actor_id INTEGER, p_reason TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    current_status TEXT;
    owner_id INTEGER;
    assigned_id INTEGER;
    actor_role TEXT;
    booking_ids JSONB;
    line_ids JSONB;
    registration_ids JSONB;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
    local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Singapore';
BEGIN
    IF btrim(COALESCE(p_reason, '')) = '' THEN
        RETURN NULL;
    END IF;
    PERFORM 1 FROM public.venue_bookings
    WHERE event_id = p_event_id ORDER BY id FOR UPDATE;
    PERFORM 1 FROM public.equipment_requests
    WHERE event_id = p_event_id ORDER BY id FOR UPDATE;
    SELECT status::text, organiser_id, coordinator_id
    INTO current_status, owner_id, assigned_id
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_status <> p_expected_status
        OR current_status IN ('Completed', 'Cancelled', 'Rejected') THEN
        RETURN NULL;
    END IF;
    SELECT role::text INTO actor_role FROM public.users WHERE id = p_actor_id;
    IF NOT (
        (actor_role = 'Event Organiser' AND owner_id = p_actor_id)
        OR (actor_role = 'Event Coordinator' AND assigned_id = p_actor_id
            AND current_status <> 'Draft')
    ) THEN
        RETURN NULL;
    END IF;

    UPDATE public.events
    SET status = 'Cancelled', updated_at = changed_at, registration_open = FALSE
    WHERE id = p_event_id;
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at, notes)
    VALUES (p_event_id, current_status::public.event_status, 'Cancelled',
            p_actor_id, changed_at, p_reason);

    WITH released AS (
        UPDATE public.venue_bookings
        SET status = 'Cancelled',
            cancelled_at = changed_at,
            cancelled_by_id = p_actor_id,
            cancellation_reason = p_reason
        WHERE event_id = p_event_id
          AND (status::text IN ('Requested', 'Confirmed')
               OR (status::text = 'Held' AND hold_expires_at > local_now))
        RETURNING id
    )
    SELECT COALESCE(jsonb_agg(id ORDER BY id), '[]'::jsonb) INTO booking_ids FROM released;

    WITH released AS (
        UPDATE public.equipment_requests
        SET status = 'Removed',
            version = version + 1,
            updated_at = changed_at,
            updated_by_id = p_actor_id
        WHERE event_id = p_event_id AND status <> 'Removed'
        RETURNING id
    )
    SELECT COALESCE(jsonb_agg(id ORDER BY id), '[]'::jsonb) INTO line_ids FROM released;

    WITH released AS (
        UPDATE public.registrations
        SET status = 'Event Cancelled'
        WHERE event_id = p_event_id AND status::text = 'Registered'
        RETURNING id
    )
    SELECT COALESCE(jsonb_agg(id ORDER BY id), '[]'::jsonb) INTO registration_ids FROM released;

    RETURN jsonb_build_object(
        'bookings', booking_ids, 'equipment', line_ids, 'registrations', registration_ids
    );
END;
$$;
REVOKE ALL ON FUNCTION public.cancel_event(INTEGER, TEXT, INTEGER, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_event(INTEGER, TEXT, INTEGER, TEXT)
    TO service_role;

-- 3. withdraw_registration, as SUPABASE_US20_2_WITHDRAW.sql has it, except that
--    a registration the event's cancellation ended answers `closed` rather than
--    `already-withdrawn`: the Attendee did not withdraw it.
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

    IF reg_status = 'Withdrawn' THEN
        RETURN jsonb_build_object('outcome', 'already-withdrawn');
    END IF;
    IF reg_status <> 'Registered' OR event_status IS DISTINCT FROM 'Confirmed' THEN
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

-- Verify the status and the two functions.
SELECT enumlabel FROM pg_enum
WHERE enumtypid = 'public.registration_status'::regtype
ORDER BY enumsortorder;

SELECT proname, pg_get_function_arguments(oid)
FROM pg_proc
WHERE proname IN ('cancel_event', 'withdraw_registration')
  AND pronamespace = 'public'::regnamespace;
