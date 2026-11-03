-- D1 (CODE_AUDIT.md): an important change during the safety check sends the
-- event back to Planning.
--
-- Before this script, a Coordinator could change an event's attendance after the
-- Safety Officer approved it and then confirm it on that approval. Now an
-- important change (US5.2's rule: date, time, attendance, venue or equipment)
-- to an event that is Pending Safety Check moves it back to Planning, whether
-- the Coordinator edits it directly (us11_edit) or accepts an Organiser's change
-- request (us11_approve_change). Back in Planning it must be sent for the safety
-- check again and get a fresh decision (US17.2) before the Coordinator can
-- confirm it (US4.7). Routine changes, such as the title, leave it alone.
--
-- Run after SUPABASE_US11_2_CHANGE_REVIEW.sql, SUPABASE_US11_3_RECONFIRM.sql and
-- SUPABASE_US4_7_CONFIRM_EVENT.sql. Safe to run twice. Apply it before deploying
-- the backend that sends p_reason: the old backend keeps working afterwards,
-- because p_reason is optional.

BEGIN;

-- 1. Direct Coordinator edits. Same checks and writes as before, plus the move.
--    The four-argument version is dropped so PostgREST is never left choosing
--    between two overloads.
DROP FUNCTION IF EXISTS public.us11_edit(INTEGER, INTEGER, TIMESTAMP, JSONB);

CREATE OR REPLACE FUNCTION public.us11_edit(
    p_event_id INTEGER,
    p_actor_id INTEGER,
    p_updated_at TIMESTAMP,
    p_changes JSONB,
    p_reason TEXT DEFAULT NULL
) RETURNS BOOLEAN LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    e public.events;
    v_at TIMESTAMP;
BEGIN
    SELECT * INTO e FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR e.coordinator_id IS DISTINCT FROM p_actor_id OR e.updated_at <> p_updated_at
        OR e.status IN ('Draft', 'Completed', 'Cancelled', 'Rejected') OR EXISTS (
            SELECT 1 FROM public.event_change_requests
            WHERE event_id = p_event_id AND status = 'pending'
        ) THEN
        RETURN FALSE;
    END IF;
    PERFORM public.us11_apply(p_event_id, p_actor_id, p_changes);
    v_at := timezone('UTC', clock_timestamp());

    IF e.status::text = 'Pending Safety Check' AND EXISTS (
        SELECT 1 FROM jsonb_array_elements(COALESCE(p_changes, '[]'::jsonb)) AS c
        WHERE c->>'change_type' = 'important'
    ) THEN
        UPDATE public.events
        SET status = 'Planning'::text::public.event_status, updated_at = v_at
        WHERE id = p_event_id;
        INSERT INTO public.status_changes
            (event_id, old_status, new_status, changed_by_id, changed_at, notes)
        VALUES (p_event_id, 'Pending Safety Check', 'Planning', p_actor_id, v_at,
                NULLIF(btrim(COALESCE(p_reason, '')), ''));
    ELSE
        UPDATE public.events SET updated_at = v_at WHERE id = p_event_id;
    END IF;
    RETURN TRUE;
END $$;
REVOKE ALL ON FUNCTION public.us11_edit(INTEGER, INTEGER, TIMESTAMP, JSONB, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.us11_edit(INTEGER, INTEGER, TIMESTAMP, JSONB, TEXT)
    TO service_role;

-- 2. Accepted change requests. As SUPABASE_US11_3_RECONFIRM.sql, except that an
--    event Pending Safety Check reopens too, and the history entry records the
--    status it actually left.
CREATE OR REPLACE FUNCTION public.us11_approve_change(
    p_event_id INTEGER,
    p_actor_id INTEGER,
    p_revision INTEGER,
    p_payload JSONB,
    p_reason TEXT
) RETURNS BOOLEAN LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_status TEXT;
    v_important BOOLEAN;
    v_at TIMESTAMP;
BEGIN
    SELECT status::text INTO v_status FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;
    -- Read before us11_review answers the rows: afterwards none is pending.
    SELECT EXISTS (
        SELECT 1 FROM public.event_change_requests
        WHERE event_id = p_event_id AND status = 'pending' AND change_type = 'important'
    ) INTO v_important;

    IF NOT public.us11_review(p_event_id, p_actor_id, 'approve', p_revision, p_payload) THEN
        RETURN FALSE;
    END IF;

    IF v_status IN ('Confirmed', 'Pending Safety Check') AND v_important THEN
        v_at := timezone('UTC', clock_timestamp());
        UPDATE public.events
        SET status = 'Planning'::text::public.event_status, updated_at = v_at
        WHERE id = p_event_id;
        INSERT INTO public.status_changes
            (event_id, old_status, new_status, changed_by_id, changed_at, notes)
        VALUES (p_event_id, v_status::public.event_status, 'Planning', p_actor_id, v_at,
                NULLIF(btrim(COALESCE(p_reason, '')), ''));
    END IF;
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.us11_approve_change(INTEGER, INTEGER, INTEGER, JSONB, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.us11_approve_change(INTEGER, INTEGER, INTEGER, JSONB, TEXT)
    TO service_role;

NOTIFY pgrst, 'reload schema';

COMMIT;

-- Verify: one us11_edit, with the optional reason.
SELECT proname, pg_get_function_identity_arguments(oid) AS args
FROM pg_proc
WHERE proname IN ('us11_edit', 'us11_approve_change')
  AND pronamespace = 'public'::regnamespace;
