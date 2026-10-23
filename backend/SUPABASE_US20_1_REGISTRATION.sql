-- US20.1: an Attendee registers for a Confirmed event, up to the capacity the
-- assigned Coordinator set.
-- Apply once to an existing Supabase project, after
-- SUPABASE_ADD_SAFETY_CHECK_STATUS.sql (US4.4, which made Confirmed reachable)
-- and SUPABASE_ADD_BOOKING_DECISIONS.sql (US16.1, the latest list of notice
-- kinds), and before deploying the registration routes. Safe to run
-- repeatedly: every statement is IF NOT EXISTS, CREATE OR REPLACE, or drops
-- what it re-adds.
--
-- Without it, the registration card on an event and the Attendee's events page
-- return 500; every other route is unaffected, because nothing else reads the
-- new columns or the new table.
--
-- The Attendee role needs no change here: 'Attendee' has been in `user_role`
-- since SUPABASE_SETUP.sql. The development accounts are made by
-- seed_new_users.py --attendees-only.

-- 1. Registration settings, one pair per event. Off until the assigned
--    Coordinator turns it on. A capacity is kept when registration is turned
--    off again, so turning it back on starts from the same number.
ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS registration_open BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS registration_capacity INTEGER;
ALTER TABLE public.events
    DROP CONSTRAINT IF EXISTS events_registration_capacity_positive;
ALTER TABLE public.events
    ADD CONSTRAINT events_registration_capacity_positive CHECK (
        registration_capacity IS NULL OR registration_capacity >= 1
    );
ALTER TABLE public.events
    DROP CONSTRAINT IF EXISTS events_registration_open_has_capacity;
ALTER TABLE public.events
    ADD CONSTRAINT events_registration_open_has_capacity CHECK (
        NOT registration_open OR registration_capacity IS NOT NULL
    );

-- 2. Only the status this story produces. US20.2 (withdrawing) and US4.6
--    (Event Cancelled) add theirs with ALTER TYPE ... ADD VALUE.
DO $$
BEGIN
    CREATE TYPE public.registration_status AS ENUM ('Registered');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS public.registrations (
    id SERIAL PRIMARY KEY,
    -- A registration means nothing without its event, as with venue_bookings.
    event_id INTEGER NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
    -- The Attendee's account: what "one registration per Attendee" counts by.
    attendee_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    -- What the Attendee gave on the form. Both required.
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    status public.registration_status NOT NULL DEFAULT 'Registered',
    -- Naive UTC, like every other recorded time; the page shows it in
    -- Singapore time.
    created_at TIMESTAMP NOT NULL DEFAULT timezone('UTC', now()),
    CONSTRAINT registrations_name_given CHECK (btrim(name) <> ''),
    CONSTRAINT registrations_email_given CHECK (btrim(email) <> '')
);

-- One active registration per Attendee per event. Partial, so a registration
-- withdrawn under US20.2 stays as history and the Attendee may register again.
CREATE UNIQUE INDEX IF NOT EXISTS ux_registrations_one_active_per_attendee
    ON public.registrations (event_id, attendee_id)
    WHERE status = 'Registered';
-- The read paths: an event's places taken, and an Attendee's own registrations.
CREATE INDEX IF NOT EXISTS ix_registrations_event_status
    ON public.registrations (event_id, status);
CREATE INDEX IF NOT EXISTS ix_registrations_attendee_id
    ON public.registrations (attendee_id);

-- Server-only access, as for every other table (see SUPABASE_HARDENING.sql).
ALTER TABLE public.registrations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.registrations FROM anon, authenticated;

-- 3. The capacity, enforced in the database whoever writes the row. Every
--    registration that becomes active locks its event first, so two at once
--    for the last place queue on that lock: the second one counts after the
--    first has committed, finds the event full and is refused.
--
--    Each statement in a plpgsql function takes a fresh snapshot, so the count
--    below, run after the lock is granted, sees the registration that held it.
CREATE OR REPLACE FUNCTION public.enforce_registration_capacity()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    current_status TEXT;
    is_open BOOLEAN;
    places INTEGER;
    taken INTEGER;
BEGIN
    IF NEW.status::text <> 'Registered' THEN
        RETURN NEW;
    END IF;
    -- Nested rather than one AND: OLD is NULL on INSERT.
    IF TG_OP = 'UPDATE' THEN
        IF OLD.status::text = 'Registered' THEN
            RETURN NEW;
        END IF;
    END IF;
    SELECT status::text, registration_open, registration_capacity
    INTO current_status, is_open, places
    FROM public.events WHERE id = NEW.event_id FOR UPDATE;
    IF current_status IS DISTINCT FROM 'Confirmed' OR NOT is_open THEN
        RAISE EXCEPTION 'Registration is not open for event %', NEW.event_id
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT count(*) INTO taken FROM public.registrations
    WHERE event_id = NEW.event_id AND status = 'Registered';
    IF taken >= places THEN
        RAISE EXCEPTION 'Event is full' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS enforce_registration_capacity ON public.registrations;
CREATE TRIGGER enforce_registration_capacity
BEFORE INSERT OR UPDATE OF status ON public.registrations
FOR EACH ROW EXECUTE FUNCTION public.enforce_registration_capacity();

-- 4. Registering, with every refusal as an answer rather than an error, so the
--    API can say which one. Returns {"outcome": ...}:
--      registered          plus "id", "createdAt" and "becameFull" (this one took the last place)
--      already-registered  the Attendee already has an active registration here
--      full                no places left
--      closed              no such event, not Confirmed, or registration is off
--      not-attendee        the account is not an Attendee
--      invalid             a blank name or email
--    The event is locked before anything is counted, as in the trigger above,
--    which then re-checks the same thing under the same lock.
CREATE OR REPLACE FUNCTION public.register_for_event(
    p_event_id INTEGER, p_attendee_id INTEGER, p_name TEXT, p_email TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    attendee_role TEXT;
    current_status TEXT;
    is_open BOOLEAN;
    places INTEGER;
    taken INTEGER;
    new_id INTEGER;
    new_at TIMESTAMP;
BEGIN
    IF btrim(COALESCE(p_name, '')) = '' OR btrim(COALESCE(p_email, '')) = '' THEN
        RETURN jsonb_build_object('outcome', 'invalid');
    END IF;
    SELECT role::text INTO attendee_role FROM public.users WHERE id = p_attendee_id;
    IF attendee_role IS DISTINCT FROM 'Attendee' THEN
        RETURN jsonb_build_object('outcome', 'not-attendee');
    END IF;
    SELECT status::text, registration_open, registration_capacity
    INTO current_status, is_open, places
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_status <> 'Confirmed' OR NOT is_open THEN
        RETURN jsonb_build_object('outcome', 'closed');
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.registrations
        WHERE event_id = p_event_id AND attendee_id = p_attendee_id AND status = 'Registered'
    ) THEN
        RETURN jsonb_build_object('outcome', 'already-registered');
    END IF;
    SELECT count(*) INTO taken FROM public.registrations
    WHERE event_id = p_event_id AND status = 'Registered';
    IF taken >= places THEN
        RETURN jsonb_build_object('outcome', 'full');
    END IF;

    INSERT INTO public.registrations (event_id, attendee_id, name, email)
    VALUES (p_event_id, p_attendee_id, btrim(p_name), btrim(p_email))
    RETURNING id, created_at INTO new_id, new_at;
    RETURN jsonb_build_object(
        'outcome', 'registered',
        'id', new_id,
        'createdAt', to_char(new_at, 'YYYY-MM-DD"T"HH24:MI:SS'),
        'becameFull', taken + 1 >= places
    );
END;
$$;
REVOKE ALL ON FUNCTION public.register_for_event(INTEGER, INTEGER, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_for_event(INTEGER, INTEGER, TEXT, TEXT)
    TO service_role;

-- 5. The assigned Coordinator turns registration on or off and sets the
--    capacity. Under the same lock, so a capacity cannot be set below the
--    places a registration is taking at that moment. Returns {"outcome": ...}:
--      saved             plus "registered", the places taken
--      below-registered  plus "registered": the capacity is less than that
--      invalid           turning on without a capacity, or a capacity under 1
--      closed            plus "status": not Approved, Planning, Pending Safety
--                        Check or Confirmed
--      not-assigned      no such event, or not the actor's assigned event
--    A NULL capacity keeps the one stored, which is how registration is turned
--    off without touching it.
CREATE OR REPLACE FUNCTION public.set_event_registration(
    p_event_id INTEGER, p_actor_id INTEGER, p_open BOOLEAN, p_capacity INTEGER
) RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    actor_role TEXT;
    current_status TEXT;
    assigned_id INTEGER;
    stored_capacity INTEGER;
    capacity INTEGER;
    taken INTEGER;
BEGIN
    SELECT status::text, coordinator_id, registration_capacity
    INTO current_status, assigned_id, stored_capacity
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    SELECT role::text INTO actor_role FROM public.users WHERE id = p_actor_id;
    IF current_status IS NULL OR actor_role IS DISTINCT FROM 'Event Coordinator'
        OR assigned_id IS DISTINCT FROM p_actor_id THEN
        RETURN jsonb_build_object('outcome', 'not-assigned');
    END IF;
    IF current_status NOT IN ('Approved', 'Planning', 'Pending Safety Check', 'Confirmed') THEN
        RETURN jsonb_build_object('outcome', 'closed', 'status', current_status);
    END IF;
    capacity := COALESCE(p_capacity, stored_capacity);
    IF (p_open AND capacity IS NULL) OR capacity < 1 THEN
        RETURN jsonb_build_object('outcome', 'invalid');
    END IF;
    SELECT count(*) INTO taken FROM public.registrations
    WHERE event_id = p_event_id AND status = 'Registered';
    IF capacity < taken THEN
        RETURN jsonb_build_object('outcome', 'below-registered', 'registered', taken);
    END IF;

    UPDATE public.events
    SET registration_open = p_open, registration_capacity = capacity
    WHERE id = p_event_id;
    RETURN jsonb_build_object('outcome', 'saved', 'registered', taken);
END;
$$;
REVOKE ALL ON FUNCTION public.set_event_registration(INTEGER, INTEGER, BOOLEAN, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.set_event_registration(INTEGER, INTEGER, BOOLEAN, INTEGER)
    TO service_role;

-- 6. US10.2's notices gain one kind: the event's last place was taken. It goes
--    to the assigned Coordinator and to the Organiser. The rest of the list is
--    SUPABASE_ADD_BOOKING_DECISIONS.sql's, unchanged.
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
            'booking-confirmed',
            'booking-rejected',
            'event-full'
        )
        AND status IS NULL
        AND equipment_request_id IS NULL
    )
);

NOTIFY pgrst, 'reload schema';

-- Verify the columns, the table, the functions and the notice kinds.
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'events'
  AND column_name IN ('registration_open', 'registration_capacity');

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'registrations'
ORDER BY ordinal_position;

SELECT proname, pg_get_function_arguments(oid)
FROM pg_proc
WHERE proname IN ('register_for_event', 'set_event_registration', 'enforce_registration_capacity')
  AND pronamespace = 'public'::regnamespace;

SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'notifications_kind_valid';
