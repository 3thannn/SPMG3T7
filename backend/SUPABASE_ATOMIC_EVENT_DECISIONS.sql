-- US7.1: atomically apply a Coordinator decision and its US4.2 audit entry.
-- Apply once to an existing Supabase project before deploying US7.1.
-- Safe to run repeatedly: CREATE OR REPLACE keeps the function idempotent.
--
-- Workflow validation deliberately remains in backend/app/event_status.py.
-- This function is not a status trigger and does not affect US8.1 assignment;
-- it only supplies the transaction boundary PostgREST cannot provide across
-- two separate table requests.

CREATE OR REPLACE FUNCTION public.decide_event_status(
    p_event_id INTEGER,
    p_expected_status public.event_status,
    p_new_status public.event_status,
    p_changed_by_id INTEGER,
    p_notes TEXT DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    decision_at TIMESTAMP := NOW();
BEGIN
    UPDATE public.events
    SET status = p_new_status,
        updated_at = decision_at
    WHERE id = p_event_id
      AND status = p_expected_status;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    INSERT INTO public.status_changes (
        event_id,
        old_status,
        new_status,
        changed_by_id,
        changed_at,
        notes
    )
    VALUES (
        p_event_id,
        p_expected_status,
        p_new_status,
        p_changed_by_id,
        decision_at,
        p_notes
    );

    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.decide_event_status(
    INTEGER,
    public.event_status,
    public.event_status,
    INTEGER,
    TEXT
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.decide_event_status(
    INTEGER,
    public.event_status,
    public.event_status,
    INTEGER,
    TEXT
) TO service_role;
