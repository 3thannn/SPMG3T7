-- =============================================================================
-- TEST US20.2: does withdrawing from an event work in this project?   (saves nothing)
-- =============================================================================
-- Run in the Supabase SQL Editor after SUPABASE_US20_1_REGISTRATION.sql and
-- SUPABASE_US20_2_WITHDRAW.sql.
--
-- Everything is ONE block that always ends by raising an error on purpose.
-- Postgres undoes everything a failed block did, so the test users, events and
-- registrations it creates are all rolled back. Nothing is saved, whatever the
-- result.
--
-- So the editor ALWAYS shows an error. Read its message:
--   "US20.2 PASSED - all N checks ..."      it works
--   "US20.2 FAILED - n of N checks: ..."    which checks failed
-- Any other error, such as "function public.withdraw_registration(...) does
-- not exist", means a migration has not been applied.
-- =============================================================================

DO $$
DECLARE
    tag TEXT := substr(md5(random()::text), 1, 8);
    organiser INTEGER;
    coordinator INTEGER;
    casey INTEGER;
    morgan INTEGER;
    ev INTEGER;
    started INTEGER;
    reg_casey INTEGER;
    reg_started INTEGER;
    result JSONB;
    passed INTEGER := 0;
    failures TEXT[] := '{}';
    taken INTEGER;
    found_status TEXT;
    found_when TIMESTAMP;
BEGIN
    -- ---- A small world of its own ---------------------------------------------
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-2-organiser-' || tag || '@example.invalid', 'US20.2 Organiser', 'Event Organiser')
    RETURNING id INTO organiser;
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-2-coordinator-' || tag || '@example.invalid', 'US20.2 Coordinator', 'Event Coordinator')
    RETURNING id INTO coordinator;
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-2-casey-' || tag || '@example.invalid', 'Casey', 'Attendee') RETURNING id INTO casey;
    INSERT INTO public.users (email, name, role)
    VALUES ('us20-2-morgan-' || tag || '@example.invalid', 'Morgan', 'Attendee') RETURNING id INTO morgan;

    -- One place, starting far in the future; and one that has already started.
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status,
                               expected_attendance, proposed_date)
    VALUES ('US20.2 event ' || tag, 'Test', organiser, coordinator, 'Confirmed', 30,
            '2099-11-02 09:00') RETURNING id INTO ev;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status,
                               expected_attendance, proposed_date)
    VALUES ('US20.2 started ' || tag, 'Test', organiser, coordinator, 'Confirmed', 30,
            '2000-01-01 09:00') RETURNING id INTO started;
    PERFORM public.set_event_registration(ev, coordinator, TRUE, 1);
    PERFORM public.set_event_registration(started, coordinator, TRUE, 5);

    result := public.register_for_event(ev, casey, 'Casey Tan', 'casey@example.com');
    reg_casey := (result->>'id')::int;
    result := public.register_for_event(started, casey, 'Casey Tan', 'casey@example.com');
    reg_started := (result->>'id')::int;

    result := public.register_for_event(ev, morgan, 'Morgan Lee', 'morgan@example.com');
    IF result->>'outcome' = 'full' THEN passed := passed + 1;
    ELSE failures := failures || format('the one place was not taken: %s', result); END IF;

    -- ---- AC2: who may withdraw, and when -------------------------------------
    result := public.withdraw_registration(reg_casey, morgan);
    IF result->>'outcome' = 'not-found' THEN passed := passed + 1;
    ELSE failures := failures || format('someone else withdrew Casey: %s', result); END IF;

    result := public.withdraw_registration(reg_started, casey);
    IF result->>'outcome' = 'started' THEN passed := passed + 1;
    ELSE failures := failures || format('withdrawing after the start answered %s', result); END IF;

    result := public.withdraw_registration(reg_casey, casey);
    IF result->>'outcome' = 'withdrawn' AND result ? 'withdrawnAt' THEN passed := passed + 1;
    ELSE failures := failures || format('withdrawing answered %s', result); END IF;

    SELECT status::text, withdrawn_at INTO found_status, found_when
    FROM public.registrations WHERE id = reg_casey;
    IF found_status = 'Withdrawn' AND found_when IS NOT NULL THEN passed := passed + 1;
    ELSE failures := failures || format('the row reads %s, %s', found_status, found_when); END IF;

    result := public.withdraw_registration(reg_casey, casey);
    IF result->>'outcome' = 'already-withdrawn' THEN passed := passed + 1;
    ELSE failures := failures || format('withdrawing twice answered %s', result); END IF;

    -- ---- AC2: the place goes back -------------------------------------------
    SELECT count(*) INTO taken FROM public.registrations WHERE event_id = ev AND status = 'Registered';
    IF taken = 0 THEN passed := passed + 1;
    ELSE failures := failures || format('%s places still taken after withdrawing', taken); END IF;

    result := public.register_for_event(ev, morgan, 'Morgan Lee', 'morgan@example.com');
    IF result->>'outcome' = 'registered' THEN passed := passed + 1;
    ELSE failures := failures || format('the freed place could not be taken: %s', result); END IF;

    -- ---- AC3: registering again -----------------------------------------------
    result := public.register_for_event(ev, casey, 'Casey Tan', 'casey@example.com');
    IF result = '{"outcome": "full"}'::jsonb THEN passed := passed + 1;
    ELSE failures := failures || format('Casey got a place that was not there: %s', result); END IF;

    PERFORM public.set_event_registration(ev, coordinator, TRUE, 2);
    result := public.register_for_event(ev, casey, 'Casey Tan', 'casey@example.com');
    IF result->>'outcome' = 'registered' AND (result->>'id')::int <> reg_casey THEN
        passed := passed + 1;
    ELSE failures := failures || format('registering again answered %s', result); END IF;

    -- ---- The constraint: a Withdrawn row always says when ---------------------
    BEGIN
        UPDATE public.registrations SET status = 'Withdrawn' WHERE id = (result->>'id')::int;
        failures := failures || 'a registration was withdrawn with no time';
    EXCEPTION WHEN check_violation THEN
        passed := passed + 1;
    END;

    -- ---- Report, and roll everything back -------------------------------------
    IF cardinality(failures) = 0 THEN
        RAISE EXCEPTION 'US20.2 PASSED - all % checks. Nothing was saved: this error is raised on purpose to roll the test back.', passed;
    END IF;
    RAISE EXCEPTION 'US20.2 FAILED - % of % checks: %', cardinality(failures),
        passed + cardinality(failures), array_to_string(failures, ' | ');
END
$$;
