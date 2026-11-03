-- D3 (CODE_AUDIT.md): the owning Organiser opens and closes registration too.
--
-- Week 4 customer answers: "Registration may opens once event is confirmed;
-- organiser control timing" and "closure is based on Organiser discretion and
-- manually close the registration". The Week 4 project instructions only say
-- "where attendee registration is enabled", not who enables it, so the answer
-- stands. US20.1's assigned Coordinator keeps the switch as well.
--
-- Replaces set_event_registration (SUPABASE_US20_1_REGISTRATION.sql). Only the
-- check on who may save changes. Safe to run repeatedly. Run after the US20.1
-- script; the backend that lets an Organiser call it works either way, but until
-- this runs an Organiser's save is refused as "not assigned" (409).

CREATE OR REPLACE FUNCTION public.set_event_registration(
    p_event_id integer, p_actor_id integer, p_open boolean, p_capacity integer
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    actor_role TEXT;
    current_status TEXT;
    assigned_id INTEGER;
    owner_id INTEGER;
    stored_capacity INTEGER;
    capacity INTEGER;
    taken INTEGER;
BEGIN
    SELECT status::text, coordinator_id, organiser_id, registration_capacity
    INTO current_status, assigned_id, owner_id, stored_capacity
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    SELECT role::text INTO actor_role FROM public.users WHERE id = p_actor_id;
    IF current_status IS NULL OR NOT (
        (actor_role = 'Event Coordinator' AND assigned_id = p_actor_id)
        OR (actor_role = 'Event Organiser' AND owner_id = p_actor_id)
    ) THEN
        RETURN jsonb_build_object('outcome', 'not-assigned');
    END IF;
    IF current_status NOT IN ('Approved', 'Planning', 'Pending Safety Check', 'Confirmed') THEN
        RETURN jsonb_build_object('outcome', 'closed', 'status', current_status);
    END IF;
    capacity := COALESCE(p_capacity, stored_capacity);
    IF (p_open AND capacity IS NULL) OR capacity < 1 THEN
        RETURN jsonb_build_object('outcome', 'invalid');
    END IF;
    SELECT count(*) INTO taken FROM public.registrations
    WHERE event_id = p_event_id AND status = 'Registered';
    IF capacity < taken THEN
        RETURN jsonb_build_object('outcome', 'below-registered', 'registered', taken);
    END IF;

    UPDATE public.events
    SET registration_open = p_open, registration_capacity = capacity
    WHERE id = p_event_id;
    RETURN jsonb_build_object('outcome', 'saved', 'registered', taken);
END;
$function$;

REVOKE ALL ON FUNCTION public.set_event_registration(INTEGER, INTEGER, BOOLEAN, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.set_event_registration(INTEGER, INTEGER, BOOLEAN, INTEGER)
    TO service_role;
