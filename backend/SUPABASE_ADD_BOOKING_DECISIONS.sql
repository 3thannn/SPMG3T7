-- US16.1: Venue Staff approve or reject a venue booking request, so only
-- bookings they can support get confirmed and the Coordinator knows where they
-- stand.
-- Apply once to an existing Supabase project, after
-- SUPABASE_ADD_VENUE_HOLDS.sql, SUPABASE_ADD_VENUE_TURNAROUND.sql and
-- SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql, and before deploying the
-- /booking-requests routes. Safe to run repeatedly: every statement is
-- IF NOT EXISTS or otherwise idempotent.

ALTER TYPE public.booking_status ADD VALUE IF NOT EXISTS 'Confirmed';
ALTER TYPE public.booking_status ADD VALUE IF NOT EXISTS 'Rejected';

-- The decision, on the booking like US14.2's cancellation: a request is
-- decided at most once, and nothing moves it on afterwards. decided_at is a
-- naive UTC time, as cancelled_at is.
ALTER TABLE public.venue_bookings ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP;
ALTER TABLE public.venue_bookings ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
-- An alternative venue or time Venue Staff suggest when rejecting. Free text.
ALTER TABLE public.venue_bookings ADD COLUMN IF NOT EXISTS suggested_alternative TEXT;
-- Who decided. SET NULL so removing a user keeps the decision. Named
-- explicitly: this is the table's fourth foreign key to users.
ALTER TABLE public.venue_bookings ADD COLUMN IF NOT EXISTS decided_by_id INTEGER;
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_decided_by_id_fkey;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_decided_by_id_fkey
    FOREIGN KEY (decided_by_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- A decided booking says when, and nothing else does; a rejection says why.
-- `status::text` rather than the enum literals, because Postgres will not let
-- a value added above be used before this script commits.
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_decision_recorded;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_decision_recorded CHECK (
        (status::text IN ('Confirmed', 'Rejected')) = (decided_at IS NOT NULL)
    );
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_rejection_has_reason;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_rejection_has_reason CHECK (
        status::text <> 'Rejected'
        OR (rejection_reason IS NOT NULL AND btrim(rejection_reason) <> '')
    );

CREATE INDEX IF NOT EXISTS ix_venue_bookings_decided_by_id
    ON public.venue_bookings (decided_by_id);
-- The queue: Requested bookings, oldest first.
CREATE INDEX IF NOT EXISTS ix_venue_bookings_status_created
    ON public.venue_bookings (status, created_at);

-- US10.2's notifications gain the two decision notices for the Coordinator.
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
            'booking-rejected'
        )
        AND status IS NULL
        AND equipment_request_id IS NULL
    )
);

-- US16.1: approve one request. Requested -> Confirmed, unless the slot is
-- taken by then. This is the US15.1 placeholder rule (app/availability.py) in
-- SQL, run under a lock on the venue so approvals at one venue happen one at a
-- time and two requests for the same slot cannot both be confirmed:
--   * each booking occupies its start minus the venue's setup time to its end
--     plus its turnaround time (US9.4); back to back is not a clash;
--   * the slot is taken by a Confirmed booking, or a Held one whose expiry
--     (Singapore time, like the booking times) has not passed (US14.3).
-- Returns 'confirmed', 'clash', or 'not-requested' (missing, or no longer
-- Requested). Only this booking's row is written.
CREATE OR REPLACE FUNCTION public.approve_venue_booking(
    p_booking_id INTEGER, p_actor_id INTEGER
) RETURNS TEXT LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    booking_venue_id INTEGER;
    booking_start TIMESTAMP;
    booking_end TIMESTAMP;
    booking_status TEXT;
    setup INTERVAL;
    turnaround INTERVAL;
    local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Singapore';
BEGIN
    SELECT venue_id INTO booking_venue_id
    FROM public.venue_bookings WHERE id = p_booking_id;
    IF NOT FOUND THEN
        RETURN 'not-requested';
    END IF;
    -- Venue first, then booking: every approval takes the locks in this order.
    SELECT make_interval(mins => setup_minutes), make_interval(mins => turnaround_minutes)
    INTO setup, turnaround
    FROM public.venues WHERE id = booking_venue_id FOR UPDATE;
    SELECT start_at, end_at, status::text
    INTO booking_start, booking_end, booking_status
    FROM public.venue_bookings WHERE id = p_booking_id FOR UPDATE;
    IF booking_status <> 'Requested' THEN
        RETURN 'not-requested';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.venue_bookings other
        WHERE other.venue_id = booking_venue_id
          AND other.id <> p_booking_id
          AND (
              other.status::text = 'Confirmed'
              OR (other.status::text = 'Held' AND other.hold_expires_at > local_now)
          )
          AND other.start_at - setup < booking_end + turnaround
          AND booking_start - setup < other.end_at + turnaround
    ) THEN
        RETURN 'clash';
    END IF;
    UPDATE public.venue_bookings
    SET status = 'Confirmed',
        decided_at = timezone('UTC', clock_timestamp()),
        decided_by_id = p_actor_id
    WHERE id = p_booking_id;
    RETURN 'confirmed';
END;
$$;
REVOKE ALL ON FUNCTION public.approve_venue_booking(INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.approve_venue_booking(INTEGER, INTEGER) TO service_role;

NOTIFY pgrst, 'reload schema';

-- Verify the enum values and the new columns.
SELECT enumlabel
FROM pg_enum
WHERE enumtypid = 'public.booking_status'::regtype
ORDER BY enumsortorder;

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venue_bookings'
  AND column_name IN ('decided_at', 'decided_by_id', 'rejection_reason', 'suggested_alternative');
