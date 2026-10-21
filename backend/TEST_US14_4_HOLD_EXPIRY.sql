-- =============================================================================
-- TEST US14.4: does the hold sweep work in this project?   (saves nothing)
-- =============================================================================
-- Run in the Supabase SQL Editor after SUPABASE_US14_4_HOLD_EXPIRY.sql (step 1).
-- Step 2 (the schedule) is not needed: this calls the sweep itself.
--
-- Everything is ONE block that always ends by raising an error on purpose.
-- Postgres undoes everything a failed block did, so the test users, venue,
-- events, holds and notices it creates - and whatever the sweep did to the
-- project's real holds while it ran - are all rolled back. Nothing is saved,
-- whatever the result. That matters: an Expired hold left behind would break
-- every teammate whose code predates US14.4.
--
-- So the editor ALWAYS shows an error. Read its message:
--   "US14.4 PASSED - all N checks ..."      it works
--   "US14.4 FAILED - n of N checks: ..."    which checks failed
-- Any other error, such as "function public.sweep_tentative_holds() does not
-- exist", means step 1 has not been applied.
-- =============================================================================

DO $$
DECLARE
    now_sg TIMESTAMP := date_trunc('second', clock_timestamp() AT TIME ZONE 'Asia/Singapore');
    tag TEXT := substr(md5(random()::text), 1, 8);
    organiser INTEGER;
    coordinator INTEGER;
    venue INTEGER;
    venue_name TEXT;
    open_event INTEGER;
    open_title TEXT;
    closed_event INTEGER;
    h_expired INTEGER;
    h_due INTEGER;
    h_later INTEGER;
    h_warned INTEGER;
    h_closed_expired INTEGER;
    h_closed_due INTEGER;
    h_requested INTEGER;
    due_expiry TIMESTAMP;
    result JSONB;
    again JSONB;
    passed INTEGER := 0;
    failures TEXT[] := '{}';
    found_status TEXT;
    found_warned BOOLEAN;
    found_expiry TIMESTAMP;
    notice_count INTEGER;
    notice_message TEXT;
    notice_user INTEGER;
BEGIN
    -- ---- A small world of its own ---------------------------------------------
    INSERT INTO public.users (email, name, role)
    VALUES ('us14-4-organiser-' || tag || '@example.invalid', 'US14.4 Organiser', 'Event Organiser')
    RETURNING id INTO organiser;
    INSERT INTO public.users (email, name, role)
    VALUES ('us14-4-coordinator-' || tag || '@example.invalid', 'US14.4 Coordinator', 'Event Coordinator')
    RETURNING id INTO coordinator;
    venue_name := 'US14.4 test venue ' || tag;
    INSERT INTO public.venues (name, location, capacity)
    VALUES (venue_name, 'Test', 50) RETURNING id INTO venue;
    open_title := 'US14.4 open event ' || tag;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status)
    VALUES (open_title, 'Test', organiser, coordinator, 'Planning') RETURNING id INTO open_event;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status)
    VALUES ('US14.4 cancelled event ' || tag, 'Test', organiser, coordinator, 'Cancelled')
    RETURNING id INTO closed_event;

    -- Each hold on its own far-off day, so none of them share a slot.
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at)
    VALUES (open_event, venue, now_sg + INTERVAL '62 days', now_sg + INTERVAL '62 days 8 hours',
            'Held', 30, now_sg - INTERVAL '1 minute') RETURNING id INTO h_expired;
    due_expiry := now_sg + INTERVAL '2 hours';
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at)
    VALUES (open_event, venue, now_sg + INTERVAL '64 days', now_sg + INTERVAL '64 days 8 hours',
            'Held', 30, due_expiry) RETURNING id INTO h_due;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at)
    VALUES (open_event, venue, now_sg + INTERVAL '66 days', now_sg + INTERVAL '66 days 8 hours',
            'Held', 30, now_sg + INTERVAL '3 days') RETURNING id INTO h_later;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at, expiry_warned_at)
    VALUES (open_event, venue, now_sg + INTERVAL '68 days', now_sg + INTERVAL '68 days 8 hours',
            'Held', 30, now_sg + INTERVAL '1 hour', now_sg) RETURNING id INTO h_warned;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at)
    VALUES (closed_event, venue, now_sg + INTERVAL '70 days', now_sg + INTERVAL '70 days 8 hours',
            'Held', 30, now_sg - INTERVAL '1 minute') RETURNING id INTO h_closed_expired;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at)
    VALUES (closed_event, venue, now_sg + INTERVAL '72 days', now_sg + INTERVAL '72 days 8 hours',
            'Held', 30, now_sg + INTERVAL '2 hours') RETURNING id INTO h_closed_due;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at, requested_by_id)
    VALUES (open_event, venue, now_sg + INTERVAL '74 days', now_sg + INTERVAL '74 days 8 hours',
            'Requested', 30, now_sg - INTERVAL '1 day', coordinator) RETURNING id INTO h_requested;

    -- ---- The sweep ----------------------------------------------------------
    result := public.sweep_tentative_holds();

    -- AC2: past their expiry -> Expired. Only those.
    IF result->'expired' @> to_jsonb(h_expired) THEN passed := passed + 1;
    ELSE failures := failures || 'a hold past its expiry was not expired'; END IF;
    IF result->'expired' @> to_jsonb(h_closed_expired) THEN passed := passed + 1;
    ELSE failures := failures || 'a hold on a cancelled event was not expired'; END IF;
    IF NOT (result->'expired' @> to_jsonb(h_due) OR result->'expired' @> to_jsonb(h_later)
            OR result->'expired' @> to_jsonb(h_requested)) THEN passed := passed + 1;
    ELSE failures := failures || 'a live hold or a request was expired'; END IF;

    SELECT status::text, hold_expires_at INTO found_status, found_expiry
    FROM public.venue_bookings WHERE id = h_expired;
    IF found_status = 'Expired' THEN passed := passed + 1;
    ELSE failures := failures || format('expired hold is %s, not Expired', found_status); END IF;
    IF found_expiry = now_sg - INTERVAL '1 minute' THEN passed := passed + 1;
    ELSE failures := failures || 'the expired hold lost its expiry'; END IF;
    SELECT status::text INTO found_status FROM public.venue_bookings WHERE id = h_requested;
    IF found_status = 'Requested' THEN passed := passed + 1;
    ELSE failures := failures || 'a request that started as a hold was touched'; END IF;

    -- AC3: warned once, 24 hours ahead, only on an open event.
    IF result->'warned' @> to_jsonb(h_due) THEN passed := passed + 1;
    ELSE failures := failures || 'a hold due within 24 hours was not warned'; END IF;
    IF NOT (result->'warned' @> to_jsonb(h_later) OR result->'warned' @> to_jsonb(h_warned)
            OR result->'warned' @> to_jsonb(h_closed_due)) THEN passed := passed + 1;
    ELSE failures := failures || 'a hold was warned that should not be (too far off, already warned, or cancelled event)'; END IF;
    SELECT status::text, expiry_warned_at IS NOT NULL INTO found_status, found_warned
    FROM public.venue_bookings WHERE id = h_due;
    IF found_status = 'Held' AND found_warned THEN passed := passed + 1;
    ELSE failures := failures || 'the warned hold is not Held with expiry_warned_at set'; END IF;

    SELECT count(*) INTO notice_count FROM public.notifications WHERE event_id = closed_event;
    IF notice_count = 0 THEN passed := passed + 1;
    ELSE failures := failures || 'a notice went out about a cancelled event'; END IF;
    SELECT count(*) INTO notice_count FROM public.notifications WHERE event_id = open_event;
    IF notice_count = 2 THEN passed := passed + 1;
    ELSE failures := failures || format('%s notices for the open event, expected 2', notice_count); END IF;

    -- The exact words of app/notifications.py (notify_hold_expired / _expiring).
    SELECT user_id, message INTO notice_user, notice_message FROM public.notifications
    WHERE event_id = open_event AND kind = 'hold-expired' AND status IS NULL;
    IF notice_user = coordinator
       AND notice_message = format('The tentative hold on %s for "%s" has expired.', venue_name, open_title)
    THEN passed := passed + 1;
    ELSE failures := failures || format('expired notice wrong: %s', notice_message); END IF;
    SELECT user_id, message INTO notice_user, notice_message FROM public.notifications
    WHERE event_id = open_event AND kind = 'hold-expiring' AND status IS NULL;
    IF notice_user = coordinator
       AND notice_message = format('The tentative hold on %s for "%s" expires %s.', venue_name,
                                   open_title, to_char(due_expiry, 'DD Mon YYYY, HH24:MI'))
    THEN passed := passed + 1;
    ELSE failures := failures || format('expiring notice wrong: %s', notice_message); END IF;

    -- Nothing happens twice.
    again := public.sweep_tentative_holds();
    IF NOT (again->'expired' @> to_jsonb(h_expired) OR again->'warned' @> to_jsonb(h_due)) THEN
        passed := passed + 1;
    ELSE failures := failures || 'a second sweep expired or warned again'; END IF;
    SELECT count(*) INTO notice_count FROM public.notifications WHERE event_id = open_event;
    IF notice_count = 2 THEN passed := passed + 1;
    ELSE failures := failures || 'a second sweep sent more notices'; END IF;

    -- AC2: the slot is free; a live hold's is not.
    IF NOT public.venue_slot_clashes(venue, now_sg + INTERVAL '62 days',
                                     now_sg + INTERVAL '62 days 8 hours', NULL, TRUE) THEN
        passed := passed + 1;
    ELSE failures := failures || 'the expired hold still blocks its slot'; END IF;
    IF public.venue_slot_clashes(venue, now_sg + INTERVAL '66 days',
                                 now_sg + INTERVAL '66 days 8 hours', NULL, TRUE) THEN
        passed := passed + 1;
    ELSE failures := failures || 'a live hold no longer blocks its slot'; END IF;

    -- AC4: an Expired hold cannot be turned into a request, and keeps its expiry.
    IF public.request_held_booking(h_expired, 'Planning', coordinator) = 'not-held' THEN
        passed := passed + 1;
    ELSE failures := failures || 'an expired hold could still be requested'; END IF;
    BEGIN
        UPDATE public.venue_bookings SET hold_expires_at = NULL WHERE id = h_expired;
        failures := failures || 'an Expired hold could lose its expiry';
    EXCEPTION WHEN check_violation THEN
        passed := passed + 1;
    END;

    -- ---- Report, and roll everything back -------------------------------------
    IF cardinality(failures) = 0 THEN
        RAISE EXCEPTION 'US14.4 PASSED - all % checks. Nothing was saved: this error is raised on purpose to roll the test back.', passed;
    END IF;
    RAISE EXCEPTION 'US14.4 FAILED - % of % checks: %', cardinality(failures),
        passed + cardinality(failures), array_to_string(failures, ' | ');
END
$$;
