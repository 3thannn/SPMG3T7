-- US4.4: a Pending Safety Check stage between Planning and Confirmed, so no
-- event moves into preparation without the Safety Officer's sign-off.
-- Apply once to an existing Supabase project, after SUPABASE_US4_5_LIFECYCLE.sql,
-- SUPABASE_ADD_BOOKING_CONFLICTS.sql (US15.2) and
-- SUPABASE_ADD_EQUIPMENT_REQUESTS.sql (US19), and before deploying the
-- /events/{id}/safety-check routes. Safe to run repeatedly: every statement is
-- IF NOT EXISTS or otherwise idempotent.
--
-- Without it, sending an event for its safety check returns 500 and the
-- Safety Officer has nothing to decide; every other route is unaffected.

-- The new label, in workflow order. The literals below are compared as text
-- (`status::text`), because Postgres will not let a value added here be used
-- as an enum literal before this script commits.
ALTER TYPE public.event_status ADD VALUE IF NOT EXISTS 'Pending Safety Check' AFTER 'Planning';

-- "Event can't reach Confirmed any other way." Transition validation lives in
-- Python (US4.3's allowlist, which US4.4 extends), and the RPCs below only
-- move an event the right way. This trigger is the backstop for everything
-- else that can write a status - decide_event_status included, which applies
-- whatever status it is given - so Confirmed is only ever entered from
-- Pending Safety Check, and Pending Safety Check only from Planning.
CREATE OR REPLACE FUNCTION public.guard_safety_check_transitions()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF NEW.status::text = OLD.status::text THEN
        RETURN NEW;
    END IF;
    IF NEW.status::text = 'Confirmed' AND OLD.status::text <> 'Pending Safety Check' THEN
        RAISE EXCEPTION 'An event can only become Confirmed from Pending Safety Check (was %)',
            OLD.status;
    END IF;
    IF NEW.status::text = 'Pending Safety Check' AND OLD.status::text <> 'Planning' THEN
        RAISE EXCEPTION 'An event can only become Pending Safety Check from Planning (was %)',
            OLD.status;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS guard_safety_check_transitions ON public.events;
CREATE TRIGGER guard_safety_check_transitions
BEFORE UPDATE OF status ON public.events
FOR EACH ROW EXECUTE FUNCTION public.guard_safety_check_transitions();

-- Planning -> Pending Safety Check, for the assigned Coordinator, once the
-- event is ready. The event row is locked first: venue requests
-- (request_venue_and_plan) and equipment lines (require_planning_for_equipment_request)
-- lock it too and need Planning, so nothing new can be added between this
-- check and the move. The readiness rule matches app/safety_check.py:
--   * at least one Confirmed booking, and no Requested or unexpired Held one;
--   * no Confirmed booking flagged "Conflict - review needed" (US15.2);
--   * no equipment line still outstanding (anything but Reserved or Removed);
--   * no Organiser change request waiting for an answer (US11.1).
-- Returns FALSE, changing nothing, when any of that does not hold.
CREATE OR REPLACE FUNCTION public.send_event_to_safety_check(
    p_event_id INTEGER, p_coordinator_id INTEGER
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    current_status TEXT;
    assigned_id INTEGER;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
    local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Singapore';
BEGIN
    SELECT status::text, coordinator_id INTO current_status, assigned_id
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_status <> 'Planning'
        OR assigned_id IS DISTINCT FROM p_coordinator_id THEN
        RETURN FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.venue_bookings
                   WHERE event_id = p_event_id AND status::text = 'Confirmed')
        OR EXISTS (SELECT 1 FROM public.venue_bookings
                   WHERE event_id = p_event_id
                     AND (status::text = 'Requested'
                          OR (status::text = 'Held' AND hold_expires_at > local_now)))
        OR EXISTS (SELECT 1 FROM public.venue_bookings
                   WHERE event_id = p_event_id AND status::text = 'Confirmed'
                     AND conflict_flagged_at IS NOT NULL)
        OR EXISTS (SELECT 1 FROM public.equipment_requests
                   WHERE event_id = p_event_id AND status NOT IN ('Reserved', 'Removed'))
        OR EXISTS (SELECT 1 FROM public.event_change_requests
                   WHERE event_id = p_event_id AND status = 'pending') THEN
        RETURN FALSE;
    END IF;
    UPDATE public.events
    SET status = 'Pending Safety Check'::text::public.event_status, updated_at = changed_at
    WHERE id = p_event_id;
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at)
    VALUES (p_event_id, 'Planning', 'Pending Safety Check'::text::public.event_status,
            p_coordinator_id, changed_at);
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.send_event_to_safety_check(INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.send_event_to_safety_check(INTEGER, INTEGER)
    TO service_role;

-- Pending Safety Check -> Confirmed (signed off) or -> Planning (sent back,
-- with a note), by a Safety Officer, with its US4.2 audit entry in the same
-- transaction. Only an event still Pending Safety Check moves, so a second
-- decision on the same check returns FALSE instead of overwriting the first.
CREATE OR REPLACE FUNCTION public.decide_safety_check(
    p_event_id INTEGER, p_new_status TEXT, p_officer_id INTEGER,
    p_notes TEXT DEFAULT NULL
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    IF p_new_status NOT IN ('Confirmed', 'Planning')
        OR (p_new_status = 'Planning' AND btrim(COALESCE(p_notes, '')) = '')
        OR NOT EXISTS (SELECT 1 FROM public.users
                       WHERE id = p_officer_id AND role::text = 'Safety Officer') THEN
        RETURN FALSE;
    END IF;
    UPDATE public.events
    SET status = p_new_status::public.event_status, updated_at = changed_at
    WHERE id = p_event_id AND status::text = 'Pending Safety Check';
    IF NOT FOUND THEN RETURN FALSE; END IF;
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at, notes)
    VALUES (p_event_id, 'Pending Safety Check'::text::public.event_status,
            p_new_status::public.event_status, p_officer_id, changed_at, p_notes);
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.decide_safety_check(INTEGER, TEXT, INTEGER, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.decide_safety_check(INTEGER, TEXT, INTEGER, TEXT)
    TO service_role;

NOTIFY pgrst, 'reload schema';
