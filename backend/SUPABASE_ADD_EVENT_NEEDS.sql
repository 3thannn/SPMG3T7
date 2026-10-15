-- US2.1 (reopened in Sprint 3): an event request records what it needs.
-- Apply once to an existing Supabase project, after SUPABASE_US4_5_LIFECYCLE.sql,
-- and before deploying this change. Safe to run repeatedly: every statement is
-- IF NOT EXISTS or CREATE OR REPLACE.
--
-- Every events read selects these columns, so without them GET /events and
-- every event page return 500.
--
-- Text, the way the venue catalogue (US9.1a) stores its lists: a multi-choice
-- answer is its options joined with ", ". Nullable on purpose: a draft may
-- leave any of them unanswered (US2.2), and NULL is "not answered yet". The API
-- requires all five before an event is submitted, and checks that layout,
-- facilities and accessibility come from its fixed lists. The lists live in
-- app/event_needs.py rather than in a CHECK constraint, so they can grow
-- without a migration.
ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS venue_requirements TEXT;
ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS preferred_layout TEXT;
ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS accessibility_needs TEXT;
ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS equipment_needs TEXT;
ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS registration_needs TEXT;

-- US11.1: a change request can now propose the new fields, so approving one
-- has to apply them. This is SUPABASE_US4_5_LIFECYCLE.sql's definition with
-- one branch per new column; it still refuses a field it does not know.
CREATE OR REPLACE FUNCTION public.resolve_change_request(
    p_event_id INTEGER, p_approve BOOLEAN, p_changed_by_id INTEGER,
    p_notes TEXT DEFAULT NULL
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    review_at TIMESTAMP := timezone('UTC', clock_timestamp());
    current_status public.event_status;
    assigned_id INTEGER;
    proposed RECORD;
BEGIN
    SELECT status, coordinator_id INTO current_status, assigned_id
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_status NOT IN ('Under Review', 'Approved', 'Planning')
       OR assigned_id IS DISTINCT FROM p_changed_by_id
       OR NOT EXISTS (SELECT 1 FROM public.event_change_requests
                      WHERE event_id = p_event_id AND status = 'pending') THEN
        RETURN FALSE;
    END IF;
    IF p_approve THEN
        FOR proposed IN
            SELECT changed_field, old_value, new_value, change_type
            FROM public.event_change_requests
            WHERE event_id = p_event_id AND status = 'pending'
        LOOP
            IF proposed.changed_field = 'name' THEN
                UPDATE public.events SET name = COALESCE(proposed.new_value, '') WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'purpose' THEN
                UPDATE public.events SET purpose = NULLIF(proposed.new_value, '') WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'description' THEN
                UPDATE public.events SET description = proposed.new_value WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'proposed_date' THEN
                UPDATE public.events SET proposed_date = NULLIF(proposed.new_value, '')::TIMESTAMP WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'end_date' THEN
                UPDATE public.events SET end_date = NULLIF(proposed.new_value, '')::TIMESTAMP WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'expected_attendance' THEN
                UPDATE public.events SET expected_attendance = NULLIF(proposed.new_value, '')::INTEGER WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'venue_requirements' THEN
                UPDATE public.events SET venue_requirements = NULLIF(proposed.new_value, '') WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'preferred_layout' THEN
                UPDATE public.events SET preferred_layout = NULLIF(proposed.new_value, '') WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'accessibility_needs' THEN
                UPDATE public.events SET accessibility_needs = NULLIF(proposed.new_value, '') WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'equipment_needs' THEN
                UPDATE public.events SET equipment_needs = NULLIF(proposed.new_value, '') WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'registration_needs' THEN
                UPDATE public.events SET registration_needs = NULLIF(proposed.new_value, '') WHERE id = p_event_id;
            ELSE
                RAISE EXCEPTION 'Unsupported change field: %', proposed.changed_field;
            END IF;
            INSERT INTO public.event_changes
                (event_id, changed_field, old_value, new_value, change_type,
                 changed_by_user_id, changed_at)
            VALUES (p_event_id, proposed.changed_field, proposed.old_value,
                    proposed.new_value, proposed.change_type, p_changed_by_id,
                    review_at);
        END LOOP;
    END IF;
    UPDATE public.event_change_requests
    SET status = CASE WHEN p_approve THEN 'approved' ELSE 'rejected' END,
        reviewed_by_user_id = p_changed_by_id, reviewed_at = review_at,
        review_note = p_notes
    WHERE event_id = p_event_id AND status = 'pending';
    UPDATE public.events SET updated_at = review_at WHERE id = p_event_id;
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.resolve_change_request(INTEGER, BOOLEAN, INTEGER, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.resolve_change_request(INTEGER, BOOLEAN, INTEGER, TEXT)
    TO service_role;

-- Verify the new columns.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'events'
  AND column_name IN (
      'venue_requirements', 'preferred_layout', 'accessibility_needs',
      'equipment_needs', 'registration_needs'
  )
ORDER BY ordinal_position;
