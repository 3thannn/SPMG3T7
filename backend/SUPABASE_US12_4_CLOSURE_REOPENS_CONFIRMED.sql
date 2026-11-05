-- US12.4 (reworked for Week 9): a venue closing under a Confirmed event sends
-- the event back to Planning at once.
--
-- Week 7 change #2 said the event must not be cancelled automatically, and
-- SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql read that as "do not move it at
-- all" until the Coordinator requested a replacement. Week 9 then said such an
-- event "should trigger stakeholder notifications, offline agreement, and
-- status reverting to planning/change review". Until the replacement, the event
-- showed Confirmed with a venue it could not use. Now, when Venue Staff mark a
-- venue unavailable:
--   * each affected booking is flagged Needs replacement, as before;
--   * a Confirmed event moves to Planning, with who marked the venue and why in
--     status_changes, in the same transaction; it is never cancelled;
--   * the Coordinator gets the booking notice, as before, and a back-in-planning
--     notice; the Organiser is told the event is back in Planning.
-- us12_4_request_replacement is unchanged: by the time a replacement is
-- requested the event is already in Planning, so it no longer moves it.
--
-- Also fixed: an unexpired hold was compared with UTC, but hold_expires_at is a
-- Singapore local time like the booking times, so a hold could be flagged up to
-- eight hours after it had lapsed.
--
-- Apply once to an existing Supabase project, after
-- SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql and SUPABASE_US11_3_RECONFIRM.sql
-- (which allow Confirmed -> Planning and the back-in-planning notice). Safe to
-- run repeatedly: CREATE OR REPLACE throughout.

BEGIN;

-- The back-in-planning notice (US11.3's kind). Added only if missing, so this
-- can also be applied to a database that skipped US11.3.
DO $$ DECLARE definition TEXT; BEGIN
    SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass AND conname = 'notifications_kind_valid';
    IF definition NOT LIKE '%back-in-planning%' THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7) || ') OR (kind = ''back-in-planning'''
            || ' AND status IS NULL AND equipment_request_id IS NULL))';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.flag_bookings_for_unavailability()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    affected_booking RECORD;
    notified_events INTEGER[] := ARRAY[]::INTEGER[];
    reason_text TEXT;
    dates_text TEXT;
    note TEXT;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    reason_text := CASE NEW.reason_type
        WHEN 'maintenance' THEN 'scheduled maintenance'
        WHEN 'equipment_failure' THEN 'equipment failure'
        WHEN 'renovation' THEN 'renovation work'
        WHEN 'safety_concern' THEN 'safety concern'
        ELSE NEW.other_reason
    END;
    dates_text := to_char(NEW.start_date, 'DD Mon YYYY') || '–'
        || to_char(NEW.end_date, 'DD Mon YYYY');

    FOR affected_booking IN
        SELECT booking.id, booking.event_id, venue.name AS venue_name,
               event.coordinator_id, event.organiser_id, event.name AS event_name,
               event.status::text AS event_status
        FROM public.venue_bookings AS booking
        JOIN public.venues AS venue ON venue.id = booking.venue_id
        JOIN public.events AS event ON event.id = booking.event_id
        WHERE booking.venue_id = NEW.venue_id
          AND (
              booking.status::text IN ('Requested', 'Confirmed')
              OR (booking.status::text = 'Held'
                  AND booking.hold_expires_at > (clock_timestamp() AT TIME ZONE 'Asia/Singapore'))
          )
          AND booking.start_at - make_interval(mins => venue.setup_minutes)
              < NEW.end_date::timestamp + INTERVAL '1 day'
          AND NEW.start_date::timestamp
              < booking.end_at + make_interval(mins => venue.turnaround_minutes)
        ORDER BY booking.id
        FOR UPDATE OF booking
    LOOP
        UPDATE public.venue_bookings
        SET status = 'Needs replacement', replacement_reason = reason_text,
            flagged_by_unavailability_id = NEW.id
        WHERE id = affected_booking.id;

        IF NOT (affected_booking.event_id = ANY(notified_events)) THEN
            IF affected_booking.coordinator_id IS NOT NULL THEN
                INSERT INTO public.notifications (user_id, event_id, kind, status, message)
                VALUES (
                    affected_booking.coordinator_id, affected_booking.event_id,
                    'booking-conflict', NULL,
                    format(
                        'The booking of %s for "%s" needs attention: the venue is unavailable %s due to %s.',
                        affected_booking.venue_name, affected_booking.event_name,
                        dates_text, reason_text
                    )
                );
            END IF;
            -- Week 9: a Confirmed event goes back to Planning now, not when a
            -- replacement is requested. Locked, then moved only if still Confirmed.
            IF affected_booking.event_status = 'Confirmed' THEN
                note := format(
                    '%s is unavailable %s due to %s. A replacement venue is needed, '
                    'then the safety check and confirmation again.',
                    affected_booking.venue_name, dates_text, reason_text
                );
                UPDATE public.events
                SET status = 'Planning'::text::public.event_status, updated_at = changed_at
                WHERE id = affected_booking.event_id AND status::text = 'Confirmed';
                IF FOUND THEN
                    INSERT INTO public.status_changes
                        (event_id, old_status, new_status, changed_by_id, changed_at, notes)
                    VALUES (affected_booking.event_id, 'Confirmed', 'Planning',
                            NEW.created_by_id, changed_at, note);
                    -- In app/notifications.py's words (notify_back_in_planning):
                    -- the Coordinator, then the Organiser unless they are the same.
                    note := format('"%s" is back in Planning. %s',
                                   COALESCE(NULLIF(btrim(affected_booking.event_name), ''),
                                            'an untitled event'),
                                   note);
                    IF affected_booking.coordinator_id IS NOT NULL THEN
                        INSERT INTO public.notifications
                            (user_id, event_id, kind, status, message)
                        VALUES (affected_booking.coordinator_id, affected_booking.event_id,
                                'back-in-planning', NULL, note);
                    END IF;
                    IF affected_booking.organiser_id IS DISTINCT FROM affected_booking.coordinator_id THEN
                        INSERT INTO public.notifications
                            (user_id, event_id, kind, status, message)
                        VALUES (affected_booking.organiser_id, affected_booking.event_id,
                                'back-in-planning', NULL, note);
                    END IF;
                END IF;
            END IF;
            notified_events := array_append(notified_events, affected_booking.event_id);
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trigger_flag_bookings_on_unavailability ON public.venue_unavailability;
CREATE TRIGGER trigger_flag_bookings_on_unavailability
    AFTER INSERT ON public.venue_unavailability
    FOR EACH ROW EXECUTE FUNCTION public.flag_bookings_for_unavailability();

COMMIT;

-- Verify the trigger function.
SELECT pg_get_functiondef('public.flag_bookings_for_unavailability'::regproc)
    LIKE '%back-in-planning%' AS closure_reopens_confirmed;
