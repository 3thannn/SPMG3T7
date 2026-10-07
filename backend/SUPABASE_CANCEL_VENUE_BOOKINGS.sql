-- US14.2: a Coordinator cancels one venue booking, with a reason, and who
-- cancelled it and when are kept on the booking.
-- Apply once to an existing Supabase project, after
-- SUPABASE_ADD_VENUE_BOOKINGS.sql and before deploying
-- POST /events/{id}/bookings/{bookingId}/cancel. Safe to run repeatedly: every
-- statement is IF NOT EXISTS or otherwise idempotent.
--
-- A cancelled booking is kept rather than deleted. It stays on the event's list
-- with its reason, and it no longer holds the venue for its slot (US15.1 counts
-- only Requested bookings).

ALTER TYPE public.booking_status ADD VALUE IF NOT EXISTS 'Cancelled';

-- Columns on the booking rather than an audit table: a booking is cancelled at
-- most once, and nothing moves it on afterwards.
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP;
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;
-- Who cancelled. SET NULL so removing a user keeps the cancellation on record.
-- Named explicitly: this is the table's second foreign key to users, so
-- PostgREST needs the constraint name to tell the two apart when it embeds one.
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS cancelled_by_id INTEGER;
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_cancelled_by_id_fkey;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_cancelled_by_id_fkey
    FOREIGN KEY (cancelled_by_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- A cancelled booking has a time and a reason, and nothing else does. The API
-- refuses a blank reason first with a message; this stops a row written some
-- other way. `status::text` rather than the enum literal, because Postgres will
-- not let a value added by ALTER TYPE above be used before this script commits.
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_cancellation_recorded;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_cancellation_recorded CHECK (
        (status::text = 'Cancelled') = (
            cancelled_at IS NOT NULL
            AND cancellation_reason IS NOT NULL
            AND btrim(cancellation_reason) <> ''
        )
    );

CREATE INDEX IF NOT EXISTS ix_venue_bookings_cancelled_by_id
    ON public.venue_bookings (cancelled_by_id);

-- Verify the new columns and the enum value.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venue_bookings'
ORDER BY ordinal_position;

SELECT enumlabel
FROM pg_enum
WHERE enumtypid = 'public.booking_status'::regtype
ORDER BY enumsortorder;
