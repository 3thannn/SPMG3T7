-- US17.2: the Safety Officer approves, requests changes to, or rejects an
-- event's safety arrangements, and every decision is recorded.
-- Apply once to an existing Supabase project, after
-- SUPABASE_ADD_SAFETY_CHECK_STATUS.sql (US4.4, the status and the send RPC this
-- redefines) and SUPABASE_US20_1_REGISTRATION.sql (the latest list of notice
-- kinds), and before deploying the US17.2 routes. Safe to run repeatedly:
-- every statement is IF NOT EXISTS, CREATE OR REPLACE, or drops what it
-- re-adds.
--
-- Without it, recording a safety decision, listing an event's decisions and
-- resolving a flag return 500, and so does checking whether an event is ready
-- for its safety check. Every other route is unaffected.
--
-- US4.4's decide_safety_check RPC is left in place but the app no longer calls
-- it: every decision now goes through record_safety_decision, so none is
-- made without its safety_reviews row.

-- 1. One row per decision. The US4.2 audit entry in status_changes says the
--    event moved; this says which of the three outcomes moved it, on which
--    stay in Pending Safety Check, and with what note. "safety_reviews" is
--    the name the Week 7 change log gave it.
CREATE TABLE IF NOT EXISTS public.safety_reviews (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
    outcome TEXT NOT NULL,
    note TEXT,
    decided_by_id INTEGER NOT NULL REFERENCES public.users(id),
    -- Naive UTC, like every other recorded time.
    decided_at TIMESTAMP NOT NULL DEFAULT timezone('UTC', now()),
    -- When the event entered the Pending Safety Check this decision ended, so
    -- a decision is tied to one submission and never carried to the next.
    check_started_at TIMESTAMP NOT NULL,
    CONSTRAINT safety_reviews_outcome_valid
        CHECK (outcome IN ('approved', 'changes-requested', 'rejected')),
    -- Request changes -> note required; Reject -> reason required.
    CONSTRAINT safety_reviews_note_given
        CHECK (outcome = 'approved' OR btrim(COALESCE(note, '')) <> '')
);
CREATE INDEX IF NOT EXISTS ix_safety_reviews_event_id
    ON public.safety_reviews (event_id, decided_at DESC);

-- 2. One row per arrangement a request for changes flagged for re-review:
--    a venue booking or an equipment line, never both. Open until the
--    assigned Coordinator marks it re-reviewed.
CREATE TABLE IF NOT EXISTS public.safety_review_flags (
    id SERIAL PRIMARY KEY,
    decision_id INTEGER NOT NULL REFERENCES public.safety_reviews(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
    booking_id INTEGER REFERENCES public.venue_bookings(id) ON DELETE CASCADE,
    equipment_request_id INTEGER REFERENCES public.equipment_requests(id) ON DELETE CASCADE,
    resolved_at TIMESTAMP,
    resolved_by_id INTEGER REFERENCES public.users(id),
    CONSTRAINT safety_review_flags_one_target
        CHECK ((booking_id IS NULL) <> (equipment_request_id IS NULL)),
    CONSTRAINT safety_review_flags_resolved_together
        CHECK ((resolved_at IS NULL) = (resolved_by_id IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_safety_review_flags_event_open
    ON public.safety_review_flags (event_id) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_safety_review_flags_decision_id
    ON public.safety_review_flags (decision_id);

-- Server-only access, as for every other table (see SUPABASE_HARDENING.sql).
ALTER TABLE public.safety_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.safety_reviews FROM anon, authenticated;
ALTER TABLE public.safety_review_flags ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.safety_review_flags FROM anon, authenticated;

-- 3. Record one decision: the event's move, its audit entry, the decision and
--    its flags, in one transaction. Matches app/safety_decisions.py:
--      * approved -> Confirmed; changes-requested and rejected -> Planning;
--      * a note is required unless approved;
--      * only changes-requested flags anything, and only this event's
--        bookings and equipment lines;
--      * the event must still be Pending Safety Check and, when
--        p_check_started_at is given, still on the stay that began then.
--    The event row is locked first, so two decisions at once cannot both
--    land. Returns the new safety_reviews id, or NULL - changing nothing -
--    when any of that does not hold.
CREATE OR REPLACE FUNCTION public.record_safety_decision(
    p_event_id INTEGER,
    p_outcome TEXT,
    p_officer_id INTEGER,
    p_note TEXT DEFAULT NULL,
    p_check_started_at TIMESTAMP DEFAULT NULL,
    p_booking_ids INTEGER[] DEFAULT '{}',
    p_equipment_ids INTEGER[] DEFAULT '{}'
) RETURNS INTEGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    v_to_status TEXT;
    v_current TEXT;
    v_updated_at TIMESTAMP;
    v_entered TIMESTAMP;
    v_decision_id INTEGER;
    v_note TEXT := NULLIF(btrim(COALESCE(p_note, '')), '');
    v_bookings INTEGER[] := COALESCE(p_booking_ids, '{}');
    v_equipment INTEGER[] := COALESCE(p_equipment_ids, '{}');
    v_changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    v_to_status := CASE p_outcome
        WHEN 'approved' THEN 'Confirmed'
        WHEN 'changes-requested' THEN 'Planning'
        WHEN 'rejected' THEN 'Planning'
    END;
    IF v_to_status IS NULL
        OR (p_outcome <> 'approved' AND v_note IS NULL)
        OR (p_outcome <> 'changes-requested'
            AND (cardinality(v_bookings) > 0 OR cardinality(v_equipment) > 0))
        OR NOT EXISTS (SELECT 1 FROM public.users
                       WHERE id = p_officer_id AND role::text = 'Safety Officer') THEN
        RETURN NULL;
    END IF;

    SELECT status::text, updated_at INTO v_current, v_updated_at
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR v_current <> 'Pending Safety Check' THEN
        RETURN NULL;
    END IF;

    -- The stay this decision ends: the last move into Pending Safety Check,
    -- or the event's last change for one set up by hand (as
    -- app/safety_review.py's entered_safety_check falls back).
    SELECT max(changed_at) INTO v_entered
    FROM public.status_changes
    WHERE event_id = p_event_id AND new_status::text = 'Pending Safety Check';
    v_entered := COALESCE(v_entered, v_updated_at);
    IF p_check_started_at IS NOT NULL AND p_check_started_at <> v_entered THEN
        RETURN NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM unnest(v_bookings) AS flagged(id)
               WHERE NOT EXISTS (SELECT 1 FROM public.venue_bookings b
                                 WHERE b.id = flagged.id AND b.event_id = p_event_id))
        OR EXISTS (SELECT 1 FROM unnest(v_equipment) AS flagged(id)
                   WHERE NOT EXISTS (SELECT 1 FROM public.equipment_requests q
                                     WHERE q.id = flagged.id AND q.event_id = p_event_id)) THEN
        RETURN NULL;
    END IF;

    UPDATE public.events
    SET status = v_to_status::public.event_status, updated_at = v_changed_at
    WHERE id = p_event_id;
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at, notes)
    VALUES (p_event_id, 'Pending Safety Check'::text::public.event_status,
            v_to_status::public.event_status, p_officer_id, v_changed_at, v_note);
    INSERT INTO public.safety_reviews
        (event_id, outcome, note, decided_by_id, decided_at, check_started_at)
    VALUES (p_event_id, p_outcome, v_note, p_officer_id, v_changed_at, v_entered)
    RETURNING id INTO v_decision_id;
    INSERT INTO public.safety_review_flags (decision_id, event_id, booking_id)
    SELECT DISTINCT v_decision_id, p_event_id, flagged.id
    FROM unnest(v_bookings) AS flagged(id);
    INSERT INTO public.safety_review_flags (decision_id, event_id, equipment_request_id)
    SELECT DISTINCT v_decision_id, p_event_id, flagged.id
    FROM unnest(v_equipment) AS flagged(id);
    RETURN v_decision_id;
END;
$$;
REVOKE ALL ON FUNCTION public.record_safety_decision(
    INTEGER, TEXT, INTEGER, TEXT, TIMESTAMP, INTEGER[], INTEGER[]
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_safety_decision(
    INTEGER, TEXT, INTEGER, TEXT, TIMESTAMP, INTEGER[], INTEGER[]
) TO service_role;

-- 4. US4.4's send, with US17.2's extra refusal: an arrangement flagged for
--    re-review that the Coordinator has not marked re-reviewed. Everything
--    else is as SUPABASE_ADD_SAFETY_CHECK_STATUS.sql wrote it.
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

-- 5. The Coordinator is told about a rejection too ('safety-rejected'), beside
--    US10.2's 'safety-changes'. Every earlier kind is kept.
ALTER TABLE public.notifications DROP CONSTRAINT IF EXISTS notifications_kind_valid;
ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (
    (kind = 'event-status' AND status IS NOT NULL AND equipment_request_id IS NULL)
    OR (kind = 'equipment-request' AND status IS NULL)
    OR (
        kind IN (
            'assigned',
            'unassigned',
            'hold-expiring',
            'hold-expired',
            'booking-conflict',
            'safety-changes',
            'safety-rejected',
            'booking-confirmed',
            'booking-rejected',
            'event-full'
        )
        AND status IS NULL
        AND equipment_request_id IS NULL
    )
);

NOTIFY pgrst, 'reload schema';

-- Verify the tables, the functions and the notice kinds.
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name IN ('safety_reviews', 'safety_review_flags')
ORDER BY table_name, ordinal_position;

SELECT proname, pg_get_function_arguments(oid)
FROM pg_proc
WHERE proname IN ('record_safety_decision', 'send_event_to_safety_check')
  AND pronamespace = 'public'::regnamespace;

SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'notifications_kind_valid';
