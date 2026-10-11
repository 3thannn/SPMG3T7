-- US4.5. Apply after the coordinator assignment, venue booking, and change
-- request scripts. Existing status history is retained.

ALTER TABLE public.event_change_requests
    ADD COLUMN IF NOT EXISTS request_note TEXT;

CREATE OR REPLACE FUNCTION public.assign_event_coordinator(
    p_event_id INTEGER, p_coordinator_id INTEGER, p_assigned_by_id INTEGER
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    UPDATE public.events SET coordinator_id = p_coordinator_id,
        status = 'Under Review', updated_at = changed_at
    WHERE id = p_event_id AND status = 'Submitted' AND coordinator_id IS NULL
      AND EXISTS (SELECT 1 FROM public.users WHERE id = p_coordinator_id
                  AND role = 'Event Coordinator');
    IF NOT FOUND THEN RETURN FALSE; END IF;
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at)
    VALUES (p_event_id, 'Submitted', 'Under Review', p_assigned_by_id, changed_at);
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.assign_event_coordinator(INTEGER, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.assign_event_coordinator(INTEGER, INTEGER, INTEGER)
    TO service_role;

CREATE OR REPLACE FUNCTION public.request_venue_and_plan(
    p_event_id INTEGER, p_expected_status public.event_status,
    p_venue_id INTEGER, p_start_at TIMESTAMP, p_end_at TIMESTAMP,
    p_requested_by_id INTEGER, p_headcount INTEGER,
    p_required_layout TEXT, p_required_facilities TEXT[],
    p_accessibility_needs TEXT[]
) RETURNS INTEGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    current_status public.event_status;
    assigned_id INTEGER;
    booking_id INTEGER;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    SELECT status, coordinator_id INTO current_status, assigned_id
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_status <> p_expected_status
        OR current_status NOT IN ('Approved', 'Planning')
        OR assigned_id IS DISTINCT FROM p_requested_by_id THEN
        RETURN NULL;
    END IF;
    INSERT INTO public.venue_bookings
        (event_id, venue_id, start_at, end_at, status, requested_by_id,
         created_at, headcount, required_layout, required_facilities,
         accessibility_needs)
    VALUES
        (p_event_id, p_venue_id, p_start_at, p_end_at, 'Requested',
         p_requested_by_id, changed_at, p_headcount, p_required_layout,
         p_required_facilities, p_accessibility_needs)
    RETURNING id INTO booking_id;
    IF current_status = 'Approved' THEN
        UPDATE public.events SET status = 'Planning', updated_at = changed_at
        WHERE id = p_event_id;
        INSERT INTO public.status_changes
            (event_id, old_status, new_status, changed_by_id, changed_at)
        VALUES (p_event_id, 'Approved', 'Planning', p_requested_by_id, changed_at);
    END IF;
    RETURN booking_id;
END;
$$;
REVOKE ALL ON FUNCTION public.request_venue_and_plan(
    INTEGER, public.event_status, INTEGER, TIMESTAMP, TIMESTAMP, INTEGER,
    INTEGER, TEXT, TEXT[], TEXT[]
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.request_venue_and_plan(
    INTEGER, public.event_status, INTEGER, TIMESTAMP, TIMESTAMP, INTEGER,
    INTEGER, TEXT, TEXT[], TEXT[]
) TO service_role;

CREATE OR REPLACE FUNCTION public.complete_event_status(
    p_event_id INTEGER, p_coordinator_id INTEGER
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    UPDATE public.events SET status = 'Completed', updated_at = changed_at
    WHERE id = p_event_id AND status = 'Confirmed'
      AND coordinator_id = p_coordinator_id AND end_date IS NOT NULL
      AND (clock_timestamp() AT TIME ZONE 'Asia/Singapore') > end_date;
    IF NOT FOUND THEN RETURN FALSE; END IF;
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at)
    VALUES (p_event_id, 'Confirmed', 'Completed', p_coordinator_id, changed_at);
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.complete_event_status(INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.complete_event_status(INTEGER, INTEGER)
    TO service_role;

CREATE OR REPLACE FUNCTION public.submit_change_request(
    p_event_id INTEGER, p_expected_status public.event_status,
    p_changed_by_id INTEGER, p_changes JSONB, p_notes TEXT DEFAULT NULL
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    request_at TIMESTAMP := timezone('UTC', clock_timestamp());
    current_status public.event_status;
    assigned_id INTEGER;
    next_status public.event_status;
BEGIN
    SELECT status, coordinator_id INTO current_status, assigned_id
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_status <> p_expected_status
        OR current_status NOT IN ('Submitted', 'Under Review', 'Approved', 'Planning')
        OR EXISTS (SELECT 1 FROM public.event_change_requests
                   WHERE event_id = p_event_id AND status = 'pending') THEN
        RETURN FALSE;
    END IF;
    next_status := CASE
        WHEN current_status = 'Submitted' AND assigned_id IS NOT NULL
            THEN 'Under Review'::public.event_status
        ELSE current_status END;
    UPDATE public.events SET status = next_status, updated_at = request_at
    WHERE id = p_event_id;
    INSERT INTO public.event_change_requests
        (event_id, changed_field, old_value, new_value, change_type,
         requested_by_user_id, requested_at, request_note)
    SELECT p_event_id, change ->> 'changed_field', change ->> 'old_value',
        change ->> 'new_value', change ->> 'change_type', p_changed_by_id,
        request_at, p_notes
    FROM jsonb_array_elements(p_changes) AS change;
    IF next_status <> current_status THEN
        INSERT INTO public.status_changes
            (event_id, old_status, new_status, changed_by_id, changed_at, notes)
        VALUES (p_event_id, current_status, next_status, p_changed_by_id,
                request_at, p_notes);
    END IF;
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.submit_change_request(
    INTEGER, public.event_status, INTEGER, JSONB, TEXT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.submit_change_request(
    INTEGER, public.event_status, INTEGER, JSONB, TEXT
) TO service_role;

-- The original resolver's field application and change log behavior are kept;
-- only its status guard changes from Under Review to the statuses that can
-- carry a pending request. See the replacement below.
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

-- The superseded picker must not be used for new or backfilled assignments.
DROP FUNCTION IF EXISTS public.pick_next_coordinator();
