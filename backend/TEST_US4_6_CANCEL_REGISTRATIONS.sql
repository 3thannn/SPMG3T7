-- =============================================================================
-- TEST US4.6 (registrations): does cancelling an event end its registrations?
--                                                              (saves nothing)
-- =============================================================================
-- Run in the Supabase SQL Editor after SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql.
--
-- Everything is ONE block that always ends by raising an error on purpose.
-- Postgres undoes everything a failed block did, so the test users, event and
-- registrations it creates are all rolled back. Nothing is saved, whatever the
-- result.
--
-- So the editor ALWAYS shows an error. Read its message:
--   "US4.6 REGISTRATIONS PASSED - all N checks ..."    it works
--   "US4.6 REGISTRATIONS FAILED - n of N checks: ..."  which checks failed
-- Any other error means a migration has not been applied: this needs the US20.1,
-- US20.2 and US4.6 scripts before it.
--
-- The notices to Attendees are written by the API afterwards, so they are
-- covered by tests/test_cancel_event_us4_6.py instead.
-- =============================================================================

DO $$
DECLARE
    tag TEXT := substr(md5(random()::text), 1, 8);
    organiser INTEGER;
    coordinator INTEGER;
    casey INTEGER;
    morgan INTEGER;
    jamie INTEGER;
    ev INTEGER;
    other_ev INTEGER;
    reg_casey INTEGER;
    reg_morgan INTEGER;
    reg_other INTEGER;
    result JSONB;
    passed INTEGER := 0;
    failures TEXT[] := '{}';
    found_status TEXT;
    found_open BOOLEAN;
    found_capacity INTEGER;
BEGIN
    -- ---- A small world of its own ---------------------------------------------
    INSERT INTO public.users (email, name, role)
    VALUES ('us4-6r-organiser-' || tag || '@example.invalid', 'US4.6 Organiser', 'Event Organiser')
    RETURNING id INTO organiser;
    INSERT INTO public.users (email, name, role)
    VALUES ('us4-6r-coordinator-' || tag || '@example.invalid', 'US4.6 Coordinator', 'Event Coordinator')
    RETURNING id INTO coordinator;
    INSERT INTO public.users (email, name, role)
    VALUES ('us4-6r-casey-' || tag || '@example.invalid', 'Casey', 'Attendee') RETURNING id INTO casey;
    INSERT INTO public.users (email, name, role)
    VALUES ('us4-6r-morgan-' || tag || '@example.invalid', 'Morgan', 'Attendee') RETURNING id INTO morgan;
    INSERT INTO public.users (email, name, role)
    VALUES ('us4-6r-jamie-' || tag || '@example.invalid', 'Jamie', 'Attendee') RETURNING id INTO jamie;

    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status,
                               expected_attendance, proposed_date, registration_open, registration_capacity)
    VALUES ('US4.6 registrations ' || tag, 'Test', organiser, coordinator, 'Confirmed',
            30, '2099-11-02 09:00', TRUE, 5)
    RETURNING id INTO ev;
    INSERT INTO public.events (name, description, organiser_id, coordinator_id, status,
                               expected_attendance, proposed_date, registration_open, registration_capacity)
    VALUES ('US4.6 other event ' || tag, 'Test', organiser, coordinator, 'Confirmed',
            30, '2099-11-02 09:00', TRUE, 5)
    RETURNING id INTO other_ev;

    reg_casey := (public.register_for_event(ev, casey, 'Casey', 'casey@example.com')->>'id')::int;
    reg_morgan := (public.register_for_event(ev, morgan, 'Morgan', 'morgan@example.com')->>'id')::int;
    PERFORM public.withdraw_registration(reg_morgan, morgan);
    reg_other := (public.register_for_event(other_ev, casey, 'Casey', 'casey@example.com')->>'id')::int;

    -- ---- AC4: cancelling ends the registrations that still held a place --------
    result := public.cancel_event(ev, 'Confirmed', coordinator, 'Funding was withdrawn.');
    IF result->'registrations' = to_jsonb(ARRAY[reg_casey]) THEN passed := passed + 1;
    ELSE failures := failures || format('cancel_event released registrations %s', result->'registrations'); END IF;

    SELECT status::text INTO found_status FROM public.registrations WHERE id = reg_casey;
    IF found_status = 'Event Cancelled' THEN passed := passed + 1;
    ELSE failures := failures || format('a Registered registration became %s', found_status); END IF;

    SELECT status::text INTO found_status FROM public.registrations WHERE id = reg_morgan;
    IF found_status = 'Withdrawn' THEN passed := passed + 1;
    ELSE failures := failures || format('a Withdrawn registration became %s', found_status); END IF;

    SELECT status::text INTO found_status FROM public.registrations WHERE id = reg_other;
    IF found_status = 'Registered' THEN passed := passed + 1;
    ELSE failures := failures || 'another event''s registration was touched'; END IF;

    SELECT registration_open, registration_capacity INTO found_open, found_capacity
    FROM public.events WHERE id = ev;
    IF found_open = FALSE AND found_capacity = 5 THEN passed := passed + 1;
    ELSE failures := failures || format('registration after cancelling: open %s, capacity %s', found_open, found_capacity); END IF;

    -- ---- Afterwards: nothing to withdraw from, nothing to register for ----------
    IF public.withdraw_registration(reg_casey, casey)->>'outcome' = 'closed' THEN passed := passed + 1;
    ELSE failures := failures || 'a cancelled registration did not answer closed to a withdrawal'; END IF;

    IF public.register_for_event(ev, jamie, 'Jamie', 'jamie@example.com')->>'outcome' = 'closed' THEN
        passed := passed + 1;
    ELSE failures := failures || 'someone registered for a cancelled event'; END IF;

    -- ---- What US4.6 already did still happens ----------------------------------
    SELECT status::text INTO found_status FROM public.events WHERE id = ev;
    IF found_status = 'Cancelled' THEN passed := passed + 1;
    ELSE failures := failures || format('the event is %s', found_status); END IF;

    IF public.cancel_event(ev, 'Cancelled', coordinator, 'Again') IS NULL THEN passed := passed + 1;
    ELSE failures := failures || 'a cancelled event was cancelled again'; END IF;

    -- ---- Report, and roll everything back -------------------------------------
    IF cardinality(failures) = 0 THEN
        RAISE EXCEPTION 'US4.6 REGISTRATIONS PASSED - all % checks. Nothing was saved: this error is raised on purpose to roll the test back.', passed;
    END IF;
    RAISE EXCEPTION 'US4.6 REGISTRATIONS FAILED - % of % checks: %', cardinality(failures),
        passed + cardinality(failures), array_to_string(failures, ' | ');
END
$$;
