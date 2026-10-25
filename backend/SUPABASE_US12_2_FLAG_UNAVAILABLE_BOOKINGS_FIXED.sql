/**
 * US12.2: Flag bookings hit by venue unavailability - FIXED MIGRATION
 *
 * This version handles existing data properly before adding constraints.
 */

-- 1. Create enum for unavailability reason types
DO $$ BEGIN
    CREATE TYPE public.unavailability_reason_type AS ENUM (
        'maintenance',
        'equipment_failure',
        'renovation',
        'safety_concern',
        'other'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2. Add reason_type column WITHOUT default first
ALTER TABLE public.venue_unavailability
    ADD COLUMN IF NOT EXISTS reason_type public.unavailability_reason_type;

-- 3. Add other_reason column
ALTER TABLE public.venue_unavailability
    ADD COLUMN IF NOT EXISTS other_reason TEXT;

-- 4. Migrate existing data: copy old 'reason' to 'other_reason' and set reason_type to 'other'
-- Only for rows where reason_type is not yet set
UPDATE public.venue_unavailability
SET
    reason_type = 'other',
    other_reason = CASE
        WHEN reason IS NOT NULL AND reason != '' THEN reason
        ELSE 'Venue unavailable'
    END
WHERE reason_type IS NULL;

-- 5. Now set default for new rows
ALTER TABLE public.venue_unavailability
    ALTER COLUMN reason_type SET DEFAULT 'other';

-- 6. Make reason_type NOT NULL now that all existing rows have values
ALTER TABLE public.venue_unavailability
    ALTER COLUMN reason_type SET NOT NULL;

-- 7. Add constraint: other_reason is required when reason_type = 'other'
ALTER TABLE public.venue_unavailability
    DROP CONSTRAINT IF EXISTS venue_unavailability_other_reason_check;

ALTER TABLE public.venue_unavailability
    ADD CONSTRAINT venue_unavailability_other_reason_check
    CHECK (
        (reason_type != 'other' AND other_reason IS NULL) OR
        (reason_type = 'other' AND other_reason IS NOT NULL AND length(trim(other_reason)) > 0)
    );

-- 8. Add 'Needs replacement' to booking_status enum
ALTER TYPE public.booking_status ADD VALUE IF NOT EXISTS 'Needs replacement';

-- 9. Add replacement_reason column to venue_bookings
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS replacement_reason TEXT;

-- 10. Add unavailability_id FK to track which unavailability period flagged this booking
ALTER TABLE public.venue_bookings
    ADD COLUMN IF NOT EXISTS flagged_by_unavailability_id INTEGER REFERENCES public.venue_unavailability(id) ON DELETE SET NULL;

-- 11. Create function to calculate effective booking window (includes setup + turnaround)
CREATE OR REPLACE FUNCTION public.booking_effective_window(
    booking_starts_at TIMESTAMP,
    booking_ends_at TIMESTAMP,
    venue_setup_minutes INTEGER,
    venue_turnaround_minutes INTEGER
)
RETURNS TABLE (
    effective_start TIMESTAMP,
    effective_end TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY SELECT
        booking_starts_at - (venue_setup_minutes || ' minutes')::INTERVAL AS effective_start,
        booking_ends_at + (venue_turnaround_minutes || ' minutes')::INTERVAL AS effective_end;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 12. Create function to check if a booking window overlaps an unavailability period
CREATE OR REPLACE FUNCTION public.booking_overlaps_unavailability(
    effective_start TIMESTAMP,
    effective_end TIMESTAMP,
    unavail_start DATE,
    unavail_end DATE
)
RETURNS BOOLEAN AS $$
BEGIN
    -- Convert dates to timestamps: start_date at 00:00, end_date at 24:00 (next day 00:00)
    RETURN effective_start < (unavail_end::TIMESTAMP + INTERVAL '1 day')
       AND (unavail_start::TIMESTAMP) < effective_end;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 13. Create function to flag affected bookings when unavailability is created
CREATE OR REPLACE FUNCTION public.flag_bookings_for_unavailability()
RETURNS TRIGGER AS $$
DECLARE
    affected_booking RECORD;
    affected_count INTEGER := 0;
    notified_events INTEGER[] := ARRAY[]::INTEGER[];
    reason_text TEXT;
BEGIN
    -- Build the human-readable reason text
    IF NEW.reason_type = 'other' THEN
        reason_text := NEW.other_reason;
    ELSE
        reason_text := CASE NEW.reason_type
            WHEN 'maintenance' THEN 'scheduled maintenance'
            WHEN 'equipment_failure' THEN 'equipment failure'
            WHEN 'renovation' THEN 'renovation work'
            WHEN 'safety_concern' THEN 'safety concern'
            ELSE 'venue unavailability'
        END;
    END IF;

    -- Find all active bookings at this venue that overlap the unavailability period
    FOR affected_booking IN
        SELECT
            b.id,
            b.event_id,
            b.venue_id,
            b.starts_at,
            b.ends_at,
            v.name AS venue_name,
            v.setup_minutes,
            v.turnaround_minutes,
            e.coordinator_id,
            e.title AS event_title,
            eff_window.effective_start,
            eff_window.effective_end
        FROM public.venue_bookings b
        JOIN public.venues v ON b.venue_id = v.id
        JOIN public.events e ON b.event_id = e.id
        CROSS JOIN LATERAL public.booking_effective_window(
            b.starts_at,
            b.ends_at,
            v.setup_minutes,
            v.turnaround_minutes
        ) AS eff_window
        WHERE
            b.venue_id = NEW.venue_id
            AND b.status IN ('Requested', 'Held', 'Confirmed')  -- Active bookings only
            AND public.booking_overlaps_unavailability(
                eff_window.effective_start,
                eff_window.effective_end,
                NEW.start_date,
                NEW.end_date
            )
    LOOP
        -- Flag this booking as 'Needs replacement'
        UPDATE public.venue_bookings
        SET
            status = 'Needs replacement',
            replacement_reason = reason_text,
            flagged_by_unavailability_id = NEW.id
        WHERE id = affected_booking.id;

        affected_count := affected_count + 1;

        -- Notify the Coordinator (once per event, even if multiple bookings)
        IF affected_booking.coordinator_id IS NOT NULL
           AND NOT (affected_booking.event_id = ANY(notified_events))
        THEN
            INSERT INTO public.notifications (
                user_id,
                event_id,
                kind,
                message,
                is_read,
                created_at
            ) VALUES (
                affected_booking.coordinator_id,
                affected_booking.event_id,
                'booking-conflict',  -- Reuse existing kind from US15.2
                format(
                    'The booking of %s for "%s" needs attention: the venue is unavailable %s–%s due to %s.',
                    affected_booking.venue_name,
                    affected_booking.event_title,
                    to_char(NEW.start_date, 'DD Mon YYYY'),
                    to_char(NEW.end_date, 'DD Mon YYYY'),
                    reason_text
                ),
                false,
                NOW()
            );

            notified_events := array_append(notified_events, affected_booking.event_id);
        END IF;
    END LOOP;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 14. Create trigger to run the flagging function after unavailability insert
DROP TRIGGER IF EXISTS trigger_flag_bookings_on_unavailability ON public.venue_unavailability;

CREATE TRIGGER trigger_flag_bookings_on_unavailability
    AFTER INSERT ON public.venue_unavailability
    FOR EACH ROW
    EXECUTE FUNCTION public.flag_bookings_for_unavailability();

-- 15. Add indexes for efficient queries on flagged bookings
CREATE INDEX IF NOT EXISTS ix_venue_bookings_flagged_by_unavailability
    ON public.venue_bookings (flagged_by_unavailability_id)
    WHERE flagged_by_unavailability_id IS NOT NULL;

-- Note: Partial index on 'Needs replacement' status is deferred to a separate
-- migration because PostgreSQL requires enum values to be committed before use.
-- For now, queries can use the general status index or full table scan.

COMMENT ON COLUMN public.venue_unavailability.reason_type IS 'US12.2: Structured reason for unavailability (maintenance, equipment failure, renovation, safety concern, or other)';
COMMENT ON COLUMN public.venue_unavailability.other_reason IS 'US12.2: Custom reason text when reason_type = other';
COMMENT ON COLUMN public.venue_bookings.replacement_reason IS 'US12.2: Why this booking needs replacement (from unavailability or conflict)';
COMMENT ON COLUMN public.venue_bookings.flagged_by_unavailability_id IS 'US12.2: The venue_unavailability record that flagged this booking';
