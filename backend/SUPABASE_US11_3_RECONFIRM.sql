-- US11.3: an accepted change to an important field of a Confirmed event sends
-- it back to Planning, so it is re-checked and signed off again.
-- Apply once to an existing Supabase project, after
-- SUPABASE_US11_2_CHANGE_REVIEW.sql, SUPABASE_US11_2_REVIEW_FIXES.sql and
-- SUPABASE_ADD_SAFETY_CHECK_STATUS.sql, and before deploying the US11.3 code.
-- Safe to run repeatedly: every statement is CREATE OR REPLACE, drops what it
-- re-adds, or checks before it changes anything.
--
-- Without it, approving any change request returns 500, because the API now
-- approves through us11_approve_change. Rejecting, proposing and every other
-- route are unaffected.
--
-- us11_review is left as it is and called from the new function, rather than
-- copied into it, so a live us11_review that differs from the repo keeps
-- whatever it does.

BEGIN;

-- 1. The notice both the Organiser and the Coordinator get. Added to whatever
--    notifications_kind_valid holds now, as the US11.2 script adds its kinds,
--    so no other story's kinds are lost.
DO $$ DECLARE definition TEXT; BEGIN
    SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass AND conname = 'notifications_kind_valid';
    IF definition NOT LIKE '%back-in-planning%' THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7) || ') OR (kind = ''back-in-planning'''
            || ' AND status IS NULL AND equipment_request_id IS NULL))';
    END IF;
END $$;

-- 2. Where a Confirmed event may go: Planning (US11.3), Completed (US4.5) or
--    Cancelled (US4.6). Its own trigger, beside US4.4's
--    guard_safety_check_transitions, so that one is not replaced.
CREATE OR REPLACE FUNCTION public.guard_confirmed_transitions()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF OLD.status::text = 'Confirmed'
        AND NEW.status::text NOT IN ('Confirmed', 'Planning', 'Completed', 'Cancelled') THEN
        RAISE EXCEPTION 'A Confirmed event can only move to Planning, Completed or Cancelled (not %)',
            NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS guard_confirmed_transitions ON public.events;
CREATE TRIGGER guard_confirmed_transitions
BEFORE UPDATE OF status ON public.events
FOR EACH ROW EXECUTE FUNCTION public.guard_confirmed_transitions();

-- 3. Approve a change request. us11_review applies it, exactly as before; then,
--    on an event that was Confirmed, an important change (US5.2's rule, as
--    stored on each row) moves it back to Planning with a status_changes entry
--    carrying p_reason. One transaction, so the change never lands without the
--    move. Earlier statuses, and routine changes, keep their status.
--    Returns what us11_review returns: FALSE, changing nothing, when stale.
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

    IF v_status = 'Confirmed' AND v_important THEN
        v_at := timezone('UTC', clock_timestamp());
        UPDATE public.events
        SET status = 'Planning'::text::public.event_status, updated_at = v_at
        WHERE id = p_event_id;
        INSERT INTO public.status_changes
            (event_id, old_status, new_status, changed_by_id, changed_at, notes)
        VALUES (p_event_id, 'Confirmed', 'Planning', p_actor_id, v_at,
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

-- Verify the notice kind, the trigger and the function.
SELECT pg_get_constraintdef(oid) LIKE '%back-in-planning%' AS has_notice_kind
FROM pg_constraint WHERE conname = 'notifications_kind_valid';

SELECT tgname FROM pg_trigger
WHERE tgrelid = 'public.events'::regclass AND tgname = 'guard_confirmed_transitions';

SELECT proname, pg_get_function_arguments(oid)
FROM pg_proc
WHERE proname = 'us11_approve_change' AND pronamespace = 'public'::regnamespace;
