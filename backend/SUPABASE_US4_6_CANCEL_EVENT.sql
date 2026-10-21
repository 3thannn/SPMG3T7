-- US4.6: the owning Organiser or the assigned Coordinator cancels an event,
-- with a reason, and everything it held is given back.
-- Apply once to an existing Supabase project, after
-- SUPABASE_ADD_SAFETY_CHECK_STATUS.sql (US4.4), SUPABASE_ADD_BOOKING_CONFLICTS.sql
-- (US15.2) and SUPABASE_ADD_EQUIPMENT_REQUESTS.sql (US19), and before deploying
-- POST /events/{id}/cancel. Safe to run repeatedly: every statement is
-- CREATE OR REPLACE or drops what it re-adds.
--
-- Without it, cancelling an event returns 500 and nothing changes; every other
-- route is unaffected. No new column, enum value or notification kind is
-- needed: 'Cancelled' is already in both status enums, and the notices are
-- ordinary status notices (kind 'event-status', status 'Cancelled').

-- 1. A Confirmed booking can now be Cancelled, and it keeps the decision that
--    confirmed it, as the record of what was given back. US16.1's constraint
--    said only Confirmed and Rejected bookings carry a decision; Cancelled may
--    now carry one too. Every other status still may not, and a Confirmed or
--    Rejected booking still must. `status::text`, as in the scripts before.
ALTER TABLE public.venue_bookings
    DROP CONSTRAINT IF EXISTS venue_bookings_decision_recorded;
ALTER TABLE public.venue_bookings
    ADD CONSTRAINT venue_bookings_decision_recorded CHECK (
        CASE
            WHEN status::text IN ('Confirmed', 'Rejected') THEN decided_at IS NOT NULL
            WHEN status::text = 'Cancelled' THEN TRUE
            ELSE decided_at IS NULL
        END
    );

-- 2. US19 refuses to let an event leave Planning while a line is still
--    Requested. Cancelling is the exception: the same transaction removes
--    every line (step 3 of cancel_event below), so nothing is left behind.
CREATE OR REPLACE FUNCTION public.prevent_planning_exit_with_equipment_requests()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'Planning' AND NEW.status <> 'Planning'
     AND NEW.status::text <> 'Cancelled'
     AND EXISTS (SELECT 1 FROM public.equipment_requests
                 WHERE event_id = OLD.id AND status = 'Requested') THEN
    RAISE EXCEPTION 'Resolve Requested equipment lines before leaving Planning';
  END IF;
  RETURN NEW;
END $$;

-- 3. US19 lets an equipment line change only while its event is Planning.
--    A cancelled event's lines may still be released - moved to Removed, and
--    nothing else - so a line Reserved on a Confirmed event (US19.3) is given
--    back too. Every other write on a cancelled event's lines is refused.
CREATE OR REPLACE FUNCTION public.require_planning_for_equipment_request()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE current_status public.event_status;
BEGIN
  SELECT status INTO current_status FROM public.events WHERE id = NEW.event_id FOR UPDATE;
  IF current_status IS NOT DISTINCT FROM 'Planning'::public.event_status THEN
    RETURN NEW;
  END IF;
  -- Nested rather than one AND: OLD is NULL on INSERT, and plpgsql does not
  -- promise to stop at the first false operand.
  IF TG_OP = 'UPDATE' THEN
    IF current_status::text = 'Cancelled'
       AND OLD.status <> 'Removed' AND NEW.status = 'Removed' THEN
      RETURN NEW;
    END IF;
  END IF;
  RAISE EXCEPTION 'Equipment requests can only change while the event is Planning';
END $$;

-- 4. The cancellation itself, in one transaction. Returns what it released,
--    as {"bookings": [ids], "equipment": [ids]}, or NULL - changing nothing -
--    when the event is missing, has moved from p_expected_status, is already
--    Completed, Cancelled or Rejected, or is not the actor's to cancel: an
--    Organiser's own event, or (once submitted) the Coordinator's assigned one.
--
--    Locks are taken bookings, then equipment lines, then the event. That is
--    the order the other writers use (request_held_booking: booking then
--    event; the US19 triggers: line then event; approve_venue_booking: venue
--    then booking), so none of them can deadlock against this. The UPDATEs
--    after the event lock re-read the rows, so a booking or line added while
--    this waited is released too.
--
--    "Active" bookings are the ones that hold their venue (app/booking_store.py
--    HOLDS_VENUE): Requested, Confirmed, and Held until its expiry (Singapore
--    time, like the booking times). Cancelled, Rejected and expired holds are
--    history and keep their own status.
CREATE OR REPLACE FUNCTION public.cancel_event(
    p_event_id INTEGER, p_expected_status TEXT, p_actor_id INTEGER, p_reason TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
    current_status TEXT;
    owner_id INTEGER;
    assigned_id INTEGER;
    actor_role TEXT;
    booking_ids JSONB;
    line_ids JSONB;
    changed_at TIMESTAMP := timezone('UTC', clock_timestamp());
    local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Singapore';
BEGIN
    IF btrim(COALESCE(p_reason, '')) = '' THEN
        RETURN NULL;
    END IF;
    PERFORM 1 FROM public.venue_bookings
    WHERE event_id = p_event_id ORDER BY id FOR UPDATE;
    PERFORM 1 FROM public.equipment_requests
    WHERE event_id = p_event_id ORDER BY id FOR UPDATE;
    SELECT status::text, organiser_id, coordinator_id
    INTO current_status, owner_id, assigned_id
    FROM public.events WHERE id = p_event_id FOR UPDATE;
    IF NOT FOUND OR current_status <> p_expected_status
        OR current_status IN ('Completed', 'Cancelled', 'Rejected') THEN
        RETURN NULL;
    END IF;
    SELECT role::text INTO actor_role FROM public.users WHERE id = p_actor_id;
    IF NOT (
        (actor_role = 'Event Organiser' AND owner_id = p_actor_id)
        OR (actor_role = 'Event Coordinator' AND assigned_id = p_actor_id
            AND current_status <> 'Draft')
    ) THEN
        RETURN NULL;
    END IF;

    UPDATE public.events
    SET status = 'Cancelled', updated_at = changed_at
    WHERE id = p_event_id;
    INSERT INTO public.status_changes
        (event_id, old_status, new_status, changed_by_id, changed_at, notes)
    VALUES (p_event_id, current_status::public.event_status, 'Cancelled',
            p_actor_id, changed_at, p_reason);

    WITH released AS (
        UPDATE public.venue_bookings
        SET status = 'Cancelled',
            cancelled_at = changed_at,
            cancelled_by_id = p_actor_id,
            cancellation_reason = p_reason
        WHERE event_id = p_event_id
          AND (status::text IN ('Requested', 'Confirmed')
               OR (status::text = 'Held' AND hold_expires_at > local_now))
        RETURNING id
    )
    SELECT COALESCE(jsonb_agg(id ORDER BY id), '[]'::jsonb) INTO booking_ids FROM released;

    WITH released AS (
        UPDATE public.equipment_requests
        SET status = 'Removed',
            version = version + 1,
            updated_at = changed_at,
            updated_by_id = p_actor_id
        WHERE event_id = p_event_id AND status <> 'Removed'
        RETURNING id
    )
    SELECT COALESCE(jsonb_agg(id ORDER BY id), '[]'::jsonb) INTO line_ids FROM released;

    RETURN jsonb_build_object('bookings', booking_ids, 'equipment', line_ids);
END;
$$;
REVOKE ALL ON FUNCTION public.cancel_event(INTEGER, TEXT, INTEGER, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_event(INTEGER, TEXT, INTEGER, TEXT)
    TO service_role;

NOTIFY pgrst, 'reload schema';

-- Verify the function and the relaxed constraint.
SELECT proname, pg_get_function_arguments(oid)
FROM pg_proc
WHERE proname = 'cancel_event' AND pronamespace = 'public'::regnamespace;

SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'venue_bookings_decision_recorded';
