-- US4.7: the assigned Coordinator confirms the event once every approval is in.
-- Pending Safety Check -> Confirmed stops being the Safety Officer's approval
-- (US4.4) and becomes the Coordinator's own action, confirm_event, which is
-- now the only way into Confirmed.
-- Apply once to an existing Supabase project, after
-- SUPABASE_US17_2_SAFETY_DECISIONS.sql, SUPABASE_US11_2_REVIEW_FIXES.sql and
-- SUPABASE_US11_3_RECONFIRM.sql, and together with the US4.7 code.
-- Safe to run repeatedly: every statement is CREATE OR REPLACE or checks before
-- it changes anything.
--
-- Without it, confirming returns 500, and an approval still confirms the event
-- on its own, as it did before US4.7. Run before the US4.7 code is deployed
-- the other way round, and an older checkout's approval leaves the event
-- Pending Safety Check with nothing on its page to confirm it.
--
-- Three functions below replace the repo's own definitions of them
-- (record_safety_decision from US17.2; decide_safety_check and
-- guard_safety_check_transitions from US4.4). If a live copy was changed
-- outside the repo, that change is replaced too.
--
-- A status written by hand in the SQL Editor can no longer make an event
-- Confirmed. To do it anyway, in one transaction:
--   SELECT set_config('spmg.confirming_event', 'on', true);
--   UPDATE public.events SET status = 'Confirmed' WHERE id = ...;

BEGIN;

-- 1. The Coordinator is told the Safety Officer approved. Added to whatever
--    notifications_kind_valid holds now, so no other story's kinds are lost.
--    The Organiser's "confirmed" notice is an ordinary event-status notice.
DO $$ DECLARE definition TEXT; BEGIN
    SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass AND conname = 'notifications_kind_valid';
    IF definition NOT LIKE '%safety-approved%' THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7) || ') OR (kind = ''safety-approved'''
            || ' AND status IS NULL AND equipment_request_id IS NULL))';
    END IF;
END $$;

-- 2. US4.4's guard, with US4.7's rule: Confirmed only from Pending Safety
--    Check, and only through confirm_event, which says so for its own write.
CREATE OR REPLACE FUNCTION public.guard_safety_check_transitions()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF NEW.status::text = OLD.status::text THEN
        RETURN NEW;
    END IF;
    IF NEW.status::text = 'Confirmed' AND (
        OLD.status::text <> 'Pending Safety Check'
        OR current_setting('spmg.confirming_event', true) IS DISTINCT FROM 'on'
    ) THEN
        RAISE EXCEPTION 'An event only becomes Confirmed when its Coordinator confirms it (was %)',
            OLD.status;
    END IF;
    IF NEW.status::text = 'Pending Safety Check' AND OLD.status::text <> 'Planning' THEN
        RAISE EXCEPTION 'An event can only become Pending Safety Check from Planning (was %)',
            OLD.status;
    END IF;
    RETURN NEW;
END;
$$;

-- 3. US4.4's decide_safety_check no longer sets Confirmed: back to Planning,
--    with a note, is all it does now.
CREATE OR REPLACE FUNCTION public.decide_safety_check(
    p_event_id INTEGER, p_new_status TEXT, p_officer_id INTEGER,
    p_notes TEXT DEFAULT NULL
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    IF p_new_status IS DISTINCT FROM 'Planning'
        OR btrim(COALESCE(p_notes, '')) = ''
        OR NOT EXISTS (SELECT 1 FROM public.users
                       WHERE id = p_officer_id AND role::text = 'Safety Officer') THEN
        RETURN FALSE;
    END IF;
    UPDATE public.events
    SET status = 'Planning'::text::public.event_status, updated_at = changed_at
    WHERE id = p_event_id AND status::text = 'Pending Safety Check';
    IF NOT FOUND THEN RETURN FALSE; END IF;
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at, notes)
    VALUES (p_event_id, 'Pending Safety Check'::text::public.event_status,
            'Planning'::text::public.event_status, p_officer_id, changed_at, p_notes);
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.decide_safety_check(INTEGER, TEXT, INTEGER, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.decide_safety_check(INTEGER, TEXT, INTEGER, TEXT)
    TO service_role;

-- 4. US17.2's decision, with US4.7's two changes: an approval is recorded
--    without moving the event, and a stay is decided once. As before it
--    returns the new safety_reviews id, or NULL - changing nothing - when a
--    rule does not hold.
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
        WHEN 'approved' THEN 'Pending Safety Check'
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

    SELECT max(changed_at) INTO v_entered
    FROM public.status_changes
    WHERE event_id = p_event_id AND new_status::text = 'Pending Safety Check';
    v_entered := COALESCE(v_entered, v_updated_at);
    IF p_check_started_at IS NOT NULL AND p_check_started_at <> v_entered THEN
        RETURN NULL;
    END IF;
    -- US4.7: an approval leaves the event Pending Safety Check, so the stay
    -- could otherwise be decided a second time.
    IF EXISTS (SELECT 1 FROM public.safety_reviews
               WHERE event_id = p_event_id AND check_started_at = v_entered) THEN
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

    IF p_outcome <> 'approved' THEN
        UPDATE public.events
        SET status = v_to_status::public.event_status, updated_at = v_changed_at
        WHERE id = p_event_id;
        INSERT INTO public.status_changes
            (event_id, old_status, new_status, changed_by_id, changed_at, notes)
        VALUES (p_event_id, 'Pending Safety Check'::text::public.event_status,
                v_to_status::public.event_status, p_officer_id, v_changed_at, v_note);
    END IF;
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

-- 5. Confirm: the assigned Coordinator, an event Pending Safety Check, and
--    every approval in, as app/event_confirmation.py checks first:
--      * the Safety Officer approved the current stay;
--      * at least one Confirmed booking; none Requested, Needs replacement
--        or still held, and none flagged "Conflict - review needed";
--      * the arrangement recheck finished;
--      * every equipment line Reserved, and none flagged for review;
--      * no change request pending.
--    The event row is locked first. Returns FALSE, changing nothing, when any
--    of that does not hold.
CREATE OR REPLACE FUNCTION public.confirm_event(
    p_event_id INTEGER, p_coordinator_id INTEGER
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    v_status TEXT;
    v_assigned INTEGER;
    v_updated_at TIMESTAMP;
    v_recheck_pending BOOLEAN;
    v_entered TIMESTAMP;
    v_changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
    v_local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Singapore';
BEGIN
    SELECT status::text, coordinator_id, updated_at, arrangement_review_pending
    INTO v_status, v_assigned, v_updated_at, v_recheck_pending
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR v_status <> 'Pending Safety Check'
        OR v_assigned IS DISTINCT FROM p_coordinator_id
        OR v_recheck_pending THEN
        RETURN FALSE;
    END IF;

    SELECT max(changed_at) INTO v_entered
    FROM public.status_changes
    WHERE event_id = p_event_id AND new_status::text = 'Pending Safety Check';
    v_entered := COALESCE(v_entered, v_updated_at);

    IF NOT EXISTS (SELECT 1 FROM public.safety_reviews
                   WHERE event_id = p_event_id AND outcome = 'approved'
                     AND check_started_at = v_entered)
        OR NOT EXISTS (SELECT 1 FROM public.venue_bookings
                       WHERE event_id = p_event_id AND status::text = 'Confirmed')
        OR EXISTS (SELECT 1 FROM public.venue_bookings
                   WHERE event_id = p_event_id
                     AND (status::text IN ('Requested', 'Needs replacement')
                          OR (status::text = 'Held' AND hold_expires_at > v_local_now)))
        OR EXISTS (SELECT 1 FROM public.venue_bookings
                   WHERE event_id = p_event_id AND status::text = 'Confirmed'
                     AND (conflict_flagged_at IS NOT NULL
                          OR COALESCE(event_conflict_reason, '') <> ''))
        OR EXISTS (SELECT 1 FROM public.equipment_requests
                   WHERE event_id = p_event_id AND status <> 'Removed'
                     AND (status <> 'Reserved' OR COALESCE(event_conflict_reason, '') <> ''))
        OR EXISTS (SELECT 1 FROM public.event_change_requests
                   WHERE event_id = p_event_id AND status = 'pending') THEN
        RETURN FALSE;
    END IF;

    PERFORM set_config('spmg.confirming_event', 'on', true);
    UPDATE public.events
    SET status = 'Confirmed'::text::public.event_status, updated_at = v_changed_at
    WHERE id = p_event_id;
    PERFORM set_config('spmg.confirming_event', '', true);
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at)
    VALUES (p_event_id, 'Pending Safety Check'::text::public.event_status,
            'Confirmed'::text::public.event_status, p_coordinator_id, v_changed_at);
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.confirm_event(INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.confirm_event(INTEGER, INTEGER) TO service_role;

NOTIFY pgrst, 'reload schema';

COMMIT;

-- Verify everything at once: each column should be true.
SELECT
    (SELECT pg_get_constraintdef(oid) LIKE '%safety-approved%'
     FROM pg_constraint WHERE conname = 'notifications_kind_valid') AS has_notice_kind,
    (SELECT prosrc LIKE '%spmg.confirming_event%' FROM pg_proc
     WHERE proname = 'guard_safety_check_transitions'
       AND pronamespace = 'public'::regnamespace) AS guard_updated,
    (SELECT prosrc NOT LIKE '%''Confirmed''%' FROM pg_proc
     WHERE proname = 'decide_safety_check'
       AND pronamespace = 'public'::regnamespace) AS decide_no_longer_confirms,
    (SELECT prosrc LIKE '%US4.7%' FROM pg_proc
     WHERE proname = 'record_safety_decision'
       AND pronamespace = 'public'::regnamespace) AS decision_updated,
    EXISTS (SELECT 1 FROM pg_proc
            WHERE proname = 'confirm_event'
              AND pronamespace = 'public'::regnamespace) AS has_confirm_event;
