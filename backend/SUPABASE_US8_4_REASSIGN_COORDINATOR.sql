-- US8.4: the Coordinator Lead reassigns an event to a different Coordinator.
-- Apply once to an existing Supabase project, after
-- SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql and
-- SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql, and before deploying the
-- US8.4 code. Safe to run repeatedly: it is CREATE OR REPLACE.
--
-- reassign_event_coordinator was first created on the live database by a
-- repair script that was never committed. This is that function, taken from
-- the live database with pg_get_functiondef, so a fresh setup matches
-- production, with two changes for US8.4 (marked "US8.4:" below):
--   * a Completed, Cancelled or Rejected event is no longer reassigned;
--   * the history note names the Coordinators rather than giving their ids.
--
-- Without it, a fresh database cannot reassign (the API answers 409: it now
-- reassigns through this function). The live one keeps the repair script's
-- version: a finished event can still be reassigned, and the note gives ids.

BEGIN;

CREATE OR REPLACE FUNCTION public.reassign_event_coordinator(
    p_event_id INTEGER,
    p_coordinator_id INTEGER,
    p_assigned_by_id INTEGER,
    p_expected_updated_at TIMESTAMP WITHOUT TIME ZONE
) RETURNS BOOLEAN LANGUAGE plpgsql SET search_path = '' AS $function$
DECLARE
    current_event public.events%ROWTYPE;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
    previous_name TEXT;
    new_name TEXT;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = p_assigned_by_id
                   AND role = 'Event Coordinator Lead')
       OR NOT EXISTS (SELECT 1 FROM public.users WHERE id = p_coordinator_id
                      AND role = 'Event Coordinator') THEN
        RETURN FALSE;
    END IF;
    SELECT * INTO current_event FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_event.coordinator_id IS NULL
        OR current_event.updated_at IS DISTINCT FROM p_expected_updated_at
        -- US8.4: only an active event. The finished ones keep their Coordinator.
        OR current_event.status::text IN ('Completed', 'Cancelled', 'Rejected') THEN
        RETURN FALSE;
    END IF;
    IF current_event.coordinator_id = p_coordinator_id THEN RETURN TRUE; END IF;

    UPDATE public.events SET coordinator_id = p_coordinator_id, updated_at = changed_at
    WHERE id = p_event_id;

    -- US8.4: the note names both Coordinators (app/reassignment.py reads it as
    -- a reassignment by its opening words). Ids stand in for a missing name.
    SELECT COALESCE(NULLIF(btrim(name), ''), 'Coordinator ' || id) INTO previous_name
    FROM public.users WHERE id = current_event.coordinator_id;
    SELECT COALESCE(NULLIF(btrim(name), ''), 'Coordinator ' || id) INTO new_name
    FROM public.users WHERE id = p_coordinator_id;
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at, notes)
    VALUES (p_event_id, current_event.status, current_event.status,
        p_assigned_by_id, changed_at,
        format('Coordinator reassigned from %s to %s.',
               COALESCE(previous_name, 'Coordinator ' || current_event.coordinator_id),
               new_name));

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
$function$;
REVOKE ALL ON FUNCTION public.reassign_event_coordinator(INTEGER, INTEGER, INTEGER, TIMESTAMP)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reassign_event_coordinator(INTEGER, INTEGER, INTEGER, TIMESTAMP)
    TO service_role;

NOTIFY pgrst, 'reload schema';

COMMIT;

-- Verify: the function, with both US8.4 changes.
SELECT pg_get_functiondef('public.reassign_event_coordinator'::regproc)
    LIKE '%''Completed'', ''Cancelled'', ''Rejected''%' AS refuses_closed_events,
       pg_get_functiondef('public.reassign_event_coordinator'::regproc)
    LIKE '%previous_name%' AS names_the_coordinators;
