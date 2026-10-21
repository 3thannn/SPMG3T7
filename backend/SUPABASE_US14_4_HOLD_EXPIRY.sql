-- US14.4, step 1 of 2: tentative holds expire, and the Coordinator is told.
-- Apply once to an existing Supabase project, after SUPABASE_ADD_VENUE_HOLDS.sql
-- (US14.3), SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql (US10.2) and
-- SUPABASE_ADD_BOOKING_CONFLICTS.sql (US15.2). Safe to run repeatedly: every
-- statement is IF NOT EXISTS, CREATE OR REPLACE, or drops what it re-adds.
--
-- This step changes nothing on its own. It adds the Expired status, the column
-- that remembers a warning was sent, and the function that does the sweeping,
-- but nothing calls the function until step 2
-- (SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql) schedules it.
--
-- Do not run step 2 until the US14.4 code is merged and everyone has pulled it.
-- Code from before US14.4 cannot read a booking whose status is Expired, so
-- once the job starts writing it, every bookings, holds and venue page on an
-- older checkout answers 500.
--
-- A slot is freed the moment its hold expires whether or not this has run:
-- every availability check compares the expiry with the clock (US14.3). What
-- the job adds is the record - Held becomes Expired - and the notices.

-- 1. The status an expired hold ends in. History: it never holds its venue,
--    cannot be requested, and nothing moves it on.
ALTER TYPE public.booking_status ADD VALUE IF NOT EXISTS 'Expired';

-- 2. When the Coordinator was warned that the hold is about to expire, so the
--    warning goes out once. NULL until then. A naive UTC time, as the other
--    `_at` columns on this table are.
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS expiry_warned_at TIMESTAMP;

-- 3. US14.3 said a Held booking always has an expiry. An Expired one keeps it
--    too, as the record of when it lapsed. `status::text`, because Postgres
--    will not let the value added above be used before this script commits.
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_hold_has_expiry;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_hold_has_expiry CHECK (
        status::text NOT IN ('Held', 'Expired') OR hold_expires_at IS NOT NULL
    );

-- 4. The sweep the scheduled job runs. Two passes, in this order:
--
--    a. Expire. Every Held booking whose expiry has passed (Singapore time,
--       like the booking times; expiry itself counts, as in US14.3) becomes
--       Expired, and its event's Coordinator gets a 'hold-expired' notice.
--    b. Warn. Every Held booking expiring within the next 24 hours that has not
--       been warned about gets a 'hold-expiring' notice, once. A hold placed
--       with less than a day to go is warned about at the first sweep after.
--
--    Expiring first means a hold that lapsed between two sweeps gets only the
--    notice that it expired, not a late warning as well.
--
--    Nobody is told about a hold on an event with no Coordinator, or on one
--    that is Completed, Cancelled or Rejected; such a hold still expires.
--
--    The notices are worded exactly as app/notifications.py words them
--    (notify_hold_expiring, notify_hold_expired); tests/test_hold_expiry_db.py
--    checks the two agree. Each UPDATE only matches a row still Held, so two
--    sweeps at once (the job, and someone running it by hand) cannot expire or
--    warn about the same hold twice, and a hold the Coordinator turns into a
--    request while this runs is left alone.
--
--    Returns {"expired": [ids], "warned": [ids]}.
CREATE OR REPLACE FUNCTION public.sweep_tentative_holds()
RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Singapore';
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
    expired_ids JSONB;
    warned_ids JSONB;
BEGIN
    WITH expired AS (
        UPDATE public.venue_bookings
        SET status = 'Expired'
        WHERE status::text = 'Held' AND hold_expires_at <= local_now
        RETURNING id, event_id, venue_id
    ), told AS (
        INSERT INTO public.notifications (user_id, event_id, kind, status, message, created_at)
        SELECT event.coordinator_id, event.id, 'hold-expired', NULL,
               format('The tentative hold on %s for "%s" has expired.',
                      COALESCE(NULLIF(venue.name, ''), 'a venue'),
                      COALESCE(NULLIF(btrim(event.name, E' \t\r\n\f\v'), ''),
                               'an untitled event')),
               changed_at
        FROM expired
        JOIN public.events event ON event.id = expired.event_id
        LEFT JOIN public.venues venue ON venue.id = expired.venue_id
        WHERE event.coordinator_id IS NOT NULL
          AND event.status::text NOT IN ('Completed', 'Cancelled', 'Rejected')
    )
    SELECT COALESCE(jsonb_agg(id ORDER BY id), '[]'::jsonb) INTO expired_ids FROM expired;

    WITH warned AS (
        UPDATE public.venue_bookings booking
        SET expiry_warned_at = changed_at
        FROM public.events event
        WHERE event.id = booking.event_id
          AND booking.status::text = 'Held'
          AND booking.expiry_warned_at IS NULL
          AND booking.hold_expires_at > local_now
          AND booking.hold_expires_at <= local_now + INTERVAL '24 hours'
          AND event.coordinator_id IS NOT NULL
          AND event.status::text NOT IN ('Completed', 'Cancelled', 'Rejected')
        RETURNING booking.id, booking.venue_id, booking.hold_expires_at,
                  event.id AS event_id, event.name AS event_name, event.coordinator_id
    ), told AS (
        INSERT INTO public.notifications (user_id, event_id, kind, status, message, created_at)
        SELECT warned.coordinator_id, warned.event_id, 'hold-expiring', NULL,
               format('The tentative hold on %s for "%s" expires %s.',
                      COALESCE(NULLIF(venue.name, ''), 'a venue'),
                      COALESCE(NULLIF(btrim(warned.event_name, E' \t\r\n\f\v'), ''),
                               'an untitled event'),
                      to_char(warned.hold_expires_at, 'DD Mon YYYY, HH24:MI')),
               changed_at
        FROM warned
        LEFT JOIN public.venues venue ON venue.id = warned.venue_id
    )
    SELECT COALESCE(jsonb_agg(id ORDER BY id), '[]'::jsonb) INTO warned_ids FROM warned;

    RETURN jsonb_build_object('expired', expired_ids, 'warned', warned_ids);
END;
$$;
REVOKE ALL ON FUNCTION public.sweep_tentative_holds() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sweep_tentative_holds() TO service_role;

NOTIFY pgrst, 'reload schema';

-- Verify the status, the column and the function.
SELECT enumlabel FROM pg_enum
WHERE enumtypid = 'public.booking_status'::regtype ORDER BY enumsortorder;

SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venue_bookings'
  AND column_name = 'expiry_warned_at';

SELECT proname FROM pg_proc
WHERE proname = 'sweep_tentative_holds' AND pronamespace = 'public'::regnamespace;
