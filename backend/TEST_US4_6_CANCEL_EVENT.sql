-- =============================================================================
-- TEST US4.6: does cancelling an event work in this project?   (saves nothing)
-- =============================================================================
-- Run in the Supabase SQL Editor after SUPABASE_US4_6_CANCEL_EVENT.sql.
--
-- Everything is ONE block that always ends by raising an error on purpose.
-- Postgres undoes everything a failed block did, so the test users, venue,
-- events, bookings and equipment lines it creates are all rolled back.
-- Nothing is saved, whatever the result.
--
-- So the editor ALWAYS shows an error. Read its message:
--   "US4.6 PASSED - all N checks ..."      it works
--   "US4.6 FAILED - n of N checks: ..."    which checks failed
-- Any other error, such as "function public.cancel_event(...) does not exist",
-- means the migration has not been applied.
--
-- This checks the database half: the cancel_event function and the triggers.
-- The notices are written by the API afterwards, so they are covered by
-- tests/test_cancel_event_us4_6.py instead.
-- =============================================================================

DO $$
DECLARE
    now_sg TIMESTAMP := date_trunc('second', clock_timestamp() AT TIME ZONE 'Asia/Singapore');
    now_utc TIMESTAMP := timezone('UTC', clock_timestamp());
    tag TEXT := substr(md5(random()::text), 1, 8);
    organiser INTEGER;
    coordinator INTEGER;
    staff INTEGER;
    venue INTEGER;
    ev INTEGER;
    other_ev INTEGER;
    draft_own INTEGER;
    draft_assigned INTEGER;
    b_confirmed INTEGER;
    b_requested INTEGER;
    b_live_hold INTEGER;
    b_expired_hold INTEGER;
    b_rejected INTEGER;
    b_other INTEGER;
    line_requested INTEGER;
    line_removed INTEGER;
    result JSONB;
    passed INTEGER := 0;
    failures TEXT[] := '{}';
    found_status TEXT;
    found_decided BOOLEAN;
    found_by INTEGER;
    found_reason TEXT;
    found_version INTEGER;
    history_count INTEGER;
BEGIN
    -- ---- A small world of its own ---------------------------------------------
    INSERT INTO public.users (email, name, role)
    VALUES ('us4-6-organiser-' || tag || '@example.invalid', 'US4.6 Organiser', 'Event Organiser')
    RETURNING id INTO organiser;
    INSERT INTO public.users (email, name, role)
    VALUES ('us4-6-coordinator-' || tag || '@example.invalid', 'US4.6 Coordinator', 'Event Coordinator')
    RETURNING id INTO coordinator;
    INSERT INTO public.users (email, name, role)
    VALUES ('us4-6-staff-' || tag || '@example.invalid', 'US4.6 Venue Staff', 'Venue Staff')
    RETURNING id INTO staff;
    INSERT INTO public.venues (name, location, capacity)
    VALUES ('US4.6 test venue ' || tag, 'Test', 50) RETURNING id INTO venue;

    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status)
    VALUES ('US4.6 event ' || tag, 'Test', organiser, coordinator, 'Planning') RETURNING id INTO ev;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status)
    VALUES ('US4.6 other event ' || tag, 'Test', organiser, coordinator, 'Planning')
    RETURNING id INTO other_ev;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status)
    VALUES ('US4.6 own draft ' || tag, 'Test', organiser, NULL, 'Draft') RETURNING id INTO draft_own;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status)
    VALUES ('US4.6 assigned draft ' || tag, 'Test', organiser, coordinator, 'Draft')
    RETURNING id INTO draft_assigned;

    -- Each booking on its own far-off day, so none of them share a slot.
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, requested_by_id, decided_at, decided_by_id)
    VALUES (ev, venue, now_sg + INTERVAL '62 days', now_sg + INTERVAL '62 days 8 hours',
            'Confirmed', 30, coordinator, now_utc, staff) RETURNING id INTO b_confirmed;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, requested_by_id)
    VALUES (ev, venue, now_sg + INTERVAL '64 days', now_sg + INTERVAL '64 days 8 hours',
            'Requested', 30, coordinator) RETURNING id INTO b_requested;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at, held_by_id)
    VALUES (ev, venue, now_sg + INTERVAL '66 days', now_sg + INTERVAL '66 days 8 hours',
            'Held', 30, now_sg + INTERVAL '3 days', staff) RETURNING id INTO b_live_hold;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at, held_by_id)
    VALUES (ev, venue, now_sg + INTERVAL '68 days', now_sg + INTERVAL '68 days 8 hours',
            'Held', 30, now_sg - INTERVAL '1 minute', staff) RETURNING id INTO b_expired_hold;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, requested_by_id, decided_at, decided_by_id, rejection_reason)
    VALUES (ev, venue, now_sg + INTERVAL '70 days', now_sg + INTERVAL '70 days 8 hours',
            'Rejected', 30, coordinator, now_utc, staff, 'Closed for works') RETURNING id INTO b_rejected;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, requested_by_id, decided_at, decided_by_id)
    VALUES (other_ev, venue, now_sg + INTERVAL '72 days', now_sg + INTERVAL '72 days 8 hours',
            'Confirmed', 30, coordinator, now_utc, staff) RETURNING id INTO b_other;

    INSERT INTO public.equipment_requests (event_id, equipment_type, quantity, start_at, end_at, requested_by_id, updated_by_id)
    VALUES (ev, 'Projector', 2, now_sg + INTERVAL '62 days', now_sg + INTERVAL '62 days 8 hours',
            coordinator, coordinator) RETURNING id INTO line_requested;
    INSERT INTO public.equipment_requests (event_id, equipment_type, quantity, start_at, end_at, status, requested_by_id, updated_by_id)
    VALUES (ev, 'Microphone', 1, now_sg + INTERVAL '62 days', now_sg + INTERVAL '62 days 8 hours',
            'Removed', coordinator, coordinator) RETURNING id INTO line_removed;

    -- ---- Refusals change nothing ------------------------------------------------
    IF public.cancel_event(ev, 'Planning', coordinator, '   ') IS NULL THEN passed := passed + 1;
    ELSE failures := failures || 'a blank reason was accepted'; END IF;
    IF public.cancel_event(ev, 'Planning', staff, 'Not mine') IS NULL THEN passed := passed + 1;
    ELSE failures := failures || 'Venue Staff could cancel'; END IF;
    IF public.cancel_event(ev, 'Approved', coordinator, 'Stale') IS NULL THEN passed := passed + 1;
    ELSE failures := failures || 'a stale expected status was accepted'; END IF;
    SELECT status::text INTO found_status FROM public.events WHERE id = ev;
    IF found_status = 'Planning' THEN passed := passed + 1;
    ELSE failures := failures || 'a refused cancel still changed the event'; END IF;

    -- ---- AC1/AC2: the assigned Coordinator cancels -------------------------------
    result := public.cancel_event(ev, 'Planning', coordinator, 'Funding was withdrawn.');
    IF result IS NOT NULL THEN passed := passed + 1;
    ELSE failures := failures || 'the assigned Coordinator could not cancel'; END IF;
    SELECT status::text INTO found_status FROM public.events WHERE id = ev;
    IF found_status = 'Cancelled' THEN passed := passed + 1;
    ELSE failures := failures || format('the event is %s, not Cancelled', found_status); END IF;
    SELECT count(*) INTO history_count FROM public.status_changes
    WHERE event_id = ev AND old_status::text = 'Planning' AND new_status::text = 'Cancelled'
      AND changed_by_id = coordinator AND notes = 'Funding was withdrawn.' AND changed_at IS NOT NULL;
    IF history_count = 1 THEN passed := passed + 1;
    ELSE failures := failures || 'no history entry with who, when and why'; END IF;

    -- ---- AC3: active bookings and holds released, nothing else ------------------
    IF result->'bookings' = jsonb_build_array(b_confirmed, b_requested, b_live_hold) THEN
        passed := passed + 1;
    ELSE failures := failures || format('released bookings %s', result->'bookings'); END IF;
    SELECT status::text, decided_at IS NOT NULL, cancelled_by_id, cancellation_reason
    INTO found_status, found_decided, found_by, found_reason
    FROM public.venue_bookings WHERE id = b_confirmed;
    IF found_status = 'Cancelled' AND found_decided AND found_by = coordinator
       AND found_reason = 'Funding was withdrawn.' THEN passed := passed + 1;
    ELSE failures := failures || 'the Confirmed booking was not cancelled with its decision kept'; END IF;
    SELECT count(*) INTO history_count FROM public.venue_bookings
    WHERE id IN (b_requested, b_live_hold) AND status::text = 'Cancelled';
    IF history_count = 2 THEN passed := passed + 1;
    ELSE failures := failures || 'the request or the live hold was not cancelled'; END IF;
    SELECT count(*) INTO history_count FROM public.venue_bookings
    WHERE (id = b_expired_hold AND status::text = 'Held')
       OR (id = b_rejected AND status::text = 'Rejected')
       OR (id = b_other AND status::text = 'Confirmed');
    IF history_count = 3 THEN passed := passed + 1;
    ELSE failures := failures || 'an expired hold, a rejection or another event''s booking was touched'; END IF;
    IF NOT public.venue_slot_clashes(venue, now_sg + INTERVAL '62 days',
                                     now_sg + INTERVAL '62 days 8 hours', NULL, TRUE) THEN
        passed := passed + 1;
    ELSE failures := failures || 'the released slot is still taken'; END IF;

    -- ---- AC3: equipment released -------------------------------------------------
    IF result->'equipment' = jsonb_build_array(line_requested) THEN passed := passed + 1;
    ELSE failures := failures || format('released equipment %s', result->'equipment'); END IF;
    SELECT status, updated_by_id, version INTO found_status, found_by, found_version
    FROM public.equipment_requests WHERE id = line_requested;
    IF found_status = 'Removed' AND found_by = coordinator AND found_version = 2 THEN
        passed := passed + 1;
    ELSE failures := failures || 'the equipment line was not released by the Coordinator'; END IF;
    SELECT count(*) INTO history_count FROM public.equipment_request_history
    WHERE request_id = line_requested AND action = 'Removed' AND actor_id = coordinator;
    IF history_count = 1 THEN passed := passed + 1;
    ELSE failures := failures || 'the equipment history has no Removed entry'; END IF;
    SELECT version INTO found_version FROM public.equipment_requests WHERE id = line_removed;
    IF found_version = 1 THEN passed := passed + 1;
    ELSE failures := failures || 'an already removed line was written again'; END IF;

    -- ---- AC2: read-only afterwards -----------------------------------------------
    IF public.cancel_event(ev, 'Cancelled', coordinator, 'Again') IS NULL THEN passed := passed + 1;
    ELSE failures := failures || 'a cancelled event was cancelled again'; END IF;
    BEGIN
        UPDATE public.equipment_requests SET quantity = 5 WHERE id = line_requested;
        failures := failures || 'equipment on a cancelled event could still be edited';
    EXCEPTION WHEN raise_exception THEN
        passed := passed + 1;
    END;

    -- ---- AC1: who may cancel a Draft -------------------------------------------
    IF public.cancel_event(draft_own, 'Draft', organiser, 'Not going ahead.') IS NOT NULL THEN
        passed := passed + 1;
    ELSE failures := failures || 'the Organiser could not cancel their own Draft'; END IF;
    IF public.cancel_event(draft_assigned, 'Draft', coordinator, 'Not mine yet.') IS NULL THEN
        passed := passed + 1;
    ELSE failures := failures || 'a Coordinator could cancel a Draft'; END IF;

    -- ---- Report, and roll everything back -------------------------------------
    IF cardinality(failures) = 0 THEN
        RAISE EXCEPTION 'US4.6 PASSED - all % checks. Nothing was saved: this error is raised on purpose to roll the test back.', passed;
    END IF;
    RAISE EXCEPTION 'US4.6 FAILED - % of % checks: %', cardinality(failures),
        passed + cardinality(failures), array_to_string(failures, ' | ');
END
$$;
