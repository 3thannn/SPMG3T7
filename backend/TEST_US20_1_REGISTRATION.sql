-- =============================================================================
-- TEST US20.1: does registering for an event work in this project?   (saves nothing)
-- =============================================================================
-- Run in the Supabase SQL Editor after SUPABASE_US20_1_REGISTRATION.sql.
--
-- Everything is ONE block that always ends by raising an error on purpose.
-- Postgres undoes everything a failed block did, so the test users, events and
-- registrations it creates are all rolled back. Nothing is saved, whatever the
-- result.
--
-- So the editor ALWAYS shows an error. Read its message:
--   "US20.1 PASSED - all N checks ..."      it works
--   "US20.1 FAILED - n of N checks: ..."    which checks failed
-- Any other error, such as "function public.register_for_event(...) does not
-- exist", means the migration has not been applied.
--
-- This checks the database half: the two functions, the capacity trigger, the
-- one-per-Attendee index and the notice kind. Two registrations at the same
-- moment need two connections, which the SQL Editor does not have; that is
-- tests/test_registration_db.py (TestTwoAtOnce). The notices are written by the
-- API, so they are covered by tests/test_registration_us20_1.py.
-- =============================================================================

DO $$
DECLARE
    tag TEXT := substr(md5(random()::text), 1, 8);
    organiser INTEGER;
    coordinator INTEGER;
    other_coordinator INTEGER;
    casey INTEGER;
    morgan INTEGER;
    jamie INTEGER;
    ev INTEGER;
    planning INTEGER;
    closed_off INTEGER;
    submitted INTEGER;
    roomy INTEGER;
    result JSONB;
    passed INTEGER := 0;
    failures TEXT[] := '{}';
    taken INTEGER;
    found_open BOOLEAN;
    found_capacity INTEGER;
BEGIN
    -- ---- A small world of its own ---------------------------------------------
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-1-organiser-' || tag || '@example.invalid', 'US20.1 Organiser', 'Event Organiser')
    RETURNING id INTO organiser;
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-1-coordinator-' || tag || '@example.invalid', 'US20.1 Coordinator', 'Event Coordinator')
    RETURNING id INTO coordinator;
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-1-other-' || tag || '@example.invalid', 'US20.1 Other Coordinator', 'Event Coordinator')
    RETURNING id INTO other_coordinator;
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-1-casey-' || tag || '@example.invalid', 'Casey', 'Attendee') RETURNING id INTO casey;
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-1-morgan-' || tag || '@example.invalid', 'Morgan', 'Attendee') RETURNING id INTO morgan;
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-1-jamie-' || tag || '@example.invalid', 'Jamie', 'Attendee') RETURNING id INTO jamie;

    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status, expected_attendance)
    VALUES ('US20.1 event ' || tag, 'Test', organiser, coordinator, 'Confirmed', 30) RETURNING id INTO ev;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status, expected_attendance)
    VALUES ('US20.1 planning ' || tag, 'Test', organiser, coordinator, 'Planning', 30) RETURNING id INTO planning;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status, expected_attendance)
    VALUES ('US20.1 off ' || tag, 'Test', organiser, coordinator, 'Confirmed', 30) RETURNING id INTO closed_off;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status, expected_attendance)
    VALUES ('US20.1 submitted ' || tag, 'Test', organiser, coordinator, 'Submitted', 30) RETURNING id INTO submitted;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status, expected_attendance)
    VALUES ('US20.1 roomy ' || tag, 'Test', organiser, coordinator, 'Confirmed', 30) RETURNING id INTO roomy;

    -- ---- AC1: the assigned Coordinator turns registration on --------------------
    SELECT registration_open, registration_capacity INTO found_open, found_capacity
    FROM public.events WHERE id = ev;
    IF found_open = FALSE AND found_capacity IS NULL THEN passed := passed + 1;
    ELSE failures := failures || 'a new event did not start with registration off'; END IF;

    result := public.set_event_registration(ev, coordinator, TRUE, 2);
    IF result->>'outcome' = 'saved' THEN passed := passed + 1;
    ELSE failures := failures || format('turning it on answered %s', result); END IF;

    result := public.set_event_registration(planning, coordinator, TRUE, 5);
    IF result->>'outcome' = 'saved' THEN passed := passed + 1;
    ELSE failures := failures || format('a Planning event could not be opened: %s', result); END IF;

    result := public.set_event_registration(submitted, coordinator, TRUE, 5);
    IF result->>'outcome' = 'closed' THEN passed := passed + 1;
    ELSE failures := failures || format('a Submitted event took settings: %s', result); END IF;

    result := public.set_event_registration(ev, other_coordinator, TRUE, 5);
    IF result->>'outcome' = 'not-assigned' THEN passed := passed + 1;
    ELSE failures := failures || format('another Coordinator changed the settings: %s', result); END IF;

    result := public.set_event_registration(closed_off, coordinator, TRUE, 0);
    IF result->>'outcome' = 'invalid' THEN passed := passed + 1;
    ELSE failures := failures || format('a capacity of 0 was taken: %s', result); END IF;

    result := public.set_event_registration(closed_off, coordinator, TRUE, NULL);
    IF result->>'outcome' = 'invalid' THEN passed := passed + 1;
    ELSE failures := failures || format('registration opened with no capacity: %s', result); END IF;

    -- ---- AC2/AC3: registering ---------------------------------------------------
    result := public.register_for_event(ev, casey, 'Casey Tan', 'casey@example.com');
    IF result->>'outcome' = 'registered' AND (result->>'becameFull')::boolean = FALSE THEN
        passed := passed + 1;
    ELSE failures := failures || format('the first registration answered %s', result); END IF;

    result := public.register_for_event(ev, casey, 'Casey Tan', 'casey@example.com');
    IF result->>'outcome' = 'already-registered' THEN passed := passed + 1;
    ELSE failures := failures || format('a second registration by the same Attendee answered %s', result); END IF;

    result := public.register_for_event(ev, morgan, '  ', 'morgan@example.com');
    IF result->>'outcome' = 'invalid' THEN passed := passed + 1;
    ELSE failures := failures || format('a blank name was taken: %s', result); END IF;

    result := public.register_for_event(ev, organiser, 'Dylan', 'dylan@example.com');
    IF result->>'outcome' = 'not-attendee' THEN passed := passed + 1;
    ELSE failures := failures || format('an Organiser registered: %s', result); END IF;

    result := public.register_for_event(planning, morgan, 'Morgan', 'morgan@example.com');
    IF result->>'outcome' = 'closed' THEN passed := passed + 1;
    ELSE failures := failures || format('a Planning event took a registration: %s', result); END IF;

    result := public.register_for_event(closed_off, morgan, 'Morgan', 'morgan@example.com');
    IF result->>'outcome' = 'closed' THEN passed := passed + 1;
    ELSE failures := failures || format('an event with registration off took one: %s', result); END IF;

    -- ---- AC4: the last place, then full -----------------------------------------
    result := public.register_for_event(ev, morgan, 'Morgan Lee', 'morgan@example.com');
    IF result->>'outcome' = 'registered' AND (result->>'becameFull')::boolean = TRUE THEN
        passed := passed + 1;
    ELSE failures := failures || format('the last place answered %s', result); END IF;

    result := public.register_for_event(ev, jamie, 'Jamie', 'jamie@example.com');
    IF result = '{"outcome": "full"}'::jsonb THEN passed := passed + 1;
    ELSE failures := failures || format('a full event answered %s', result); END IF;

    SELECT count(*) INTO taken FROM public.registrations WHERE event_id = ev AND status = 'Registered';
    IF taken = 2 THEN passed := passed + 1;
    ELSE failures := failures || format('%s registrations for 2 places', taken); END IF;

    -- The trigger holds even for a write that skips the function.
    BEGIN
        INSERT INTO public.registrations (event_id, attendee_id, name, email)
        VALUES (ev, jamie, 'Jamie', 'jamie@example.com');
        failures := failures || 'a direct insert went past the capacity';
    EXCEPTION WHEN check_violation THEN
        passed := passed + 1;
    END;

    BEGIN
        INSERT INTO public.registrations (event_id, attendee_id, name, email)
        VALUES (closed_off, jamie, 'Jamie', 'jamie@example.com');
        failures := failures || 'a direct insert registered for an event with registration off';
    EXCEPTION WHEN check_violation THEN
        passed := passed + 1;
    END;

    -- And the index holds one active registration per Attendee, on an event
    -- with room, so the capacity is not what refuses it.
    PERFORM public.set_event_registration(roomy, coordinator, TRUE, 10);
    PERFORM public.register_for_event(roomy, casey, 'Casey', 'casey@example.com');
    BEGIN
        INSERT INTO public.registrations (event_id, attendee_id, name, email)
        VALUES (roomy, casey, 'Casey again', 'casey@example.com');
        failures := failures || 'a second active registration for one Attendee was written';
    EXCEPTION WHEN unique_violation THEN
        passed := passed + 1;
    END;

    -- ---- AC1 again: the capacity cannot go below the places taken ---------------
    result := public.set_event_registration(ev, coordinator, TRUE, 1);
    IF result->>'outcome' = 'below-registered' AND (result->>'registered')::int = 2 THEN
        passed := passed + 1;
    ELSE failures := failures || format('a capacity below the places taken answered %s', result); END IF;

    result := public.set_event_registration(ev, coordinator, FALSE, NULL);
    SELECT registration_open, registration_capacity INTO found_open, found_capacity
    FROM public.events WHERE id = ev;
    IF result->>'outcome' = 'saved' AND found_open = FALSE AND found_capacity = 2 THEN
        passed := passed + 1;
    ELSE failures := failures || format('turning it off lost the capacity: %s, %s', found_open, found_capacity); END IF;

    -- ---- AC5: the notice kind ---------------------------------------------------
    BEGIN
        INSERT INTO public.notifications (user_id, event_id, kind, status, message)
        VALUES (organiser, ev, 'event-full', NULL, 'US20.1 test notice');
        passed := passed + 1;
    EXCEPTION WHEN check_violation THEN
        failures := failures || 'the event-full notice kind is not allowed';
    END;

    -- ---- Report, and roll everything back -------------------------------------
    IF cardinality(failures) = 0 THEN
        RAISE EXCEPTION 'US20.1 PASSED - all % checks. Nothing was saved: this error is raised on purpose to roll the test back.', passed;
    END IF;
    RAISE EXCEPTION 'US20.1 FAILED - % of % checks: %', cardinality(failures),
        passed + cardinality(failures), array_to_string(failures, ' | ');
END
$$;
