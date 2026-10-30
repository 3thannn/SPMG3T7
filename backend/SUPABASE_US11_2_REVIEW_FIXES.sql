-- Follow-up to SUPABASE_US11_2_CHANGE_REVIEW.sql, including projects that
-- already applied that migration. Apply before deploying the review fixes.
BEGIN;

-- Publish a recheck's flags and report together, or publish none of them.
-- Match cancellation's lock order: venue bookings, equipment lines, event.
CREATE OR REPLACE FUNCTION public.us11_commit_arrangement_review(
    p_event_id INTEGER, p_updated_at TIMESTAMP, p_report JSONB, p_pending BOOLEAN,
    p_booking_flags JSONB, p_equipment_flags JSONB
) RETURNS BOOLEAN LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE e public.events; f JSONB; at_time TIMESTAMP := timezone('UTC',clock_timestamp());
BEGIN
    PERFORM 1 FROM public.venue_bookings WHERE event_id=p_event_id ORDER BY id FOR UPDATE;
    PERFORM 1 FROM public.equipment_requests WHERE event_id=p_event_id ORDER BY id FOR UPDATE;
    SELECT * INTO e FROM public.events WHERE id=p_event_id FOR UPDATE;
    IF NOT FOUND OR e.updated_at IS DISTINCT FROM p_updated_at THEN RETURN FALSE; END IF;

    -- Arrangement changes while checks ran also invalidate the result. Validate
    -- the whole read set before changing any flag, including flags being cleared.
    FOR f IN SELECT * FROM jsonb_array_elements(p_booking_flags) LOOP
        IF NOT EXISTS(SELECT 1 FROM public.venue_bookings b
            WHERE b.id=(f->>'id')::INTEGER AND b.event_id=p_event_id
              AND b.status::TEXT=f->>'status'
              AND b.start_at=(f->>'startsAt')::TIMESTAMP
              AND b.end_at=(f->>'endsAt')::TIMESTAMP
              AND b.headcount IS NOT DISTINCT FROM (f->>'headcount')::INTEGER) THEN
            UPDATE public.events SET arrangement_review_pending=TRUE WHERE id=p_event_id;
            RETURN FALSE;
        END IF;
    END LOOP;
    FOR f IN SELECT * FROM jsonb_array_elements(p_equipment_flags) LOOP
        IF NOT EXISTS(SELECT 1 FROM public.equipment_requests q
            WHERE q.id=(f->>'id')::INTEGER AND q.event_id=p_event_id
              AND q.status=f->>'status' AND q.version=(f->>'version')::INTEGER) THEN
            UPDATE public.events SET arrangement_review_pending=TRUE WHERE id=p_event_id;
            RETURN FALSE;
        END IF;
    END LOOP;
    FOR f IN SELECT * FROM jsonb_array_elements(p_booking_flags) LOOP
        UPDATE public.venue_bookings SET event_conflict_reason=f->>'reason',
            event_conflict_at=CASE WHEN f->>'reason'<>'' THEN at_time ELSE NULL END
        WHERE id=(f->>'id')::INTEGER AND event_id=p_event_id
          AND event_conflict_reason IS DISTINCT FROM f->>'reason';
    END LOOP;
    FOR f IN SELECT * FROM jsonb_array_elements(p_equipment_flags) LOOP
        UPDATE public.equipment_requests SET event_conflict_reason=f->>'reason',
            event_conflict_at=CASE WHEN f->>'reason'<>'' THEN at_time ELSE NULL END
        WHERE id=(f->>'id')::INTEGER AND event_id=p_event_id
          AND event_conflict_reason IS DISTINCT FROM f->>'reason';
    END LOOP;
    UPDATE public.events SET arrangement_review=p_report, arrangement_review_pending=p_pending
        WHERE id=p_event_id;
    RETURN TRUE;
END $$;
REVOKE ALL ON FUNCTION public.us11_commit_arrangement_review(
    INTEGER,TIMESTAMP,JSONB,BOOLEAN,JSONB,JSONB) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.us11_commit_arrangement_review(
    INTEGER,TIMESTAMP,JSONB,BOOLEAN,JSONB,JSONB) TO service_role;

-- Revalidate a Reserved line against peak competing demand within its saved
-- half-open window. Ends and starts at the same instant are netted together.
-- This is independent of the existing Requested-line availability API.
CREATE OR REPLACE FUNCTION public.equipment_reservation_availability(p_request_id INTEGER)
RETURNS TABLE ("equipmentId" TEXT, name TEXT, location TEXT, "totalQuantity" INTEGER,
    "outOfServiceQuantity" INTEGER, "reservedQuantity" BIGINT,
    "availableQuantity" BIGINT, shortfall BIGINT)
LANGUAGE SQL STABLE SET search_path = '' AS $$
    SELECT e.id::TEXT, e.name::TEXT, e.location::TEXT, e.total_quantity,
        e.out_of_service_quantity, demand.peak,
        e.total_quantity::BIGINT-e.out_of_service_quantity-demand.peak,
        greatest(0::BIGINT,q.quantity-(e.total_quantity::BIGINT-e.out_of_service_quantity-demand.peak))
    FROM public.equipment_requests q
    JOIN public.equipment e ON e.id=q.equipment_id
    CROSS JOIN LATERAL (
        SELECT coalesce(max(running),0)::BIGINT AS peak FROM (
            SELECT sum(delta) OVER (ORDER BY at_time) AS running FROM (
                SELECT at_time,sum(delta) AS delta FROM (
                    SELECT greatest(r.start_at,q.start_at) AS at_time,r.quantity::BIGINT AS delta
                    FROM public.equipment_requests r
                    WHERE r.equipment_id=e.id AND r.id<>q.id AND r.status='Reserved'
                      AND r.start_at<q.end_at AND r.end_at>q.start_at
                    UNION ALL
                    SELECT least(r.end_at,q.end_at) AS at_time,-r.quantity::BIGINT AS delta
                    FROM public.equipment_requests r
                    WHERE r.equipment_id=e.id AND r.id<>q.id AND r.status='Reserved'
                      AND r.start_at<q.end_at AND r.end_at>q.start_at
                ) points GROUP BY at_time
            ) grouped_points
        ) running_demand
    ) demand
    WHERE q.id=p_request_id AND q.status='Reserved';
$$;
REVOKE ALL ON FUNCTION public.equipment_reservation_availability(INTEGER)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.equipment_reservation_availability(INTEGER) TO service_role;


-- Preserve US17.2 prerequisites and add event-change conflicts/incomplete checks.
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
    IF EXISTS (SELECT 1 FROM public.events
                WHERE id=p_event_id AND arrangement_review_pending)
        OR NOT EXISTS (SELECT 1 FROM public.venue_bookings
                   WHERE event_id = p_event_id AND status::text = 'Confirmed')
        OR EXISTS (SELECT 1 FROM public.venue_bookings
                   WHERE event_id = p_event_id
                     AND (status::text = 'Requested'
                          OR (status::text = 'Held' AND hold_expires_at > local_now)))
        OR EXISTS (SELECT 1 FROM public.venue_bookings
                   WHERE event_id = p_event_id AND status::text = 'Confirmed'
                     AND (conflict_flagged_at IS NOT NULL OR event_conflict_reason<>''))
        OR EXISTS (SELECT 1 FROM public.equipment_requests
                   WHERE event_id = p_event_id AND (status NOT IN ('Reserved', 'Removed')
                          OR (status='Reserved' AND event_conflict_reason<>'')))
        OR EXISTS (SELECT 1 FROM public.event_change_requests
                   WHERE event_id = p_event_id AND status = 'pending')
        OR EXISTS (SELECT 1 FROM public.safety_review_flags
                   WHERE event_id = p_event_id AND resolved_at IS NULL) THEN
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


NOTIFY pgrst, 'reload schema';
COMMIT;
