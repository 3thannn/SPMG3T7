-- US11.1: an Organiser requests changes to a submitted event; a Coordinator reviews them.
-- Apply once to an existing Supabase project before deploying US11.1.
-- Additive and idempotent: IF NOT EXISTS guards the table, columns and
-- indexes, and the functions use CREATE OR REPLACE.
--
-- The only table this script creates or alters is event_change_requests.
-- Everything about a request lives there: the proposed fields, whether it is
-- pending, approved or rejected, and who answered it, when and why.
--
-- The functions below also WRITE rows to tables that already exist, using
-- their current columns, so no other table's structure changes:
--
-- * events         - the move to Under Review, and the approved values.
-- * status_changes - the move to Under Review, like every other status change
--                    (US4.2). The Organiser's note travels in the existing
--                    notes column. Answering a request does not move the
--                    status, so it adds no row here.
-- * event_changes  - US5.2's log of applied changes. An approved request
--                    writes its fields here at the moment they are applied; a
--                    pending or rejected one never does.
--
-- "Change requested" is not a stored flag: an event has a request waiting
-- exactly when it has pending rows here. The functions lock the event row
-- before checking, so two requests or two answers cannot slip past each other.
--
-- Workflow validation stays in backend/app (change_requests.py, events.py).
-- These functions only supply the transaction boundary that PostgREST cannot
-- provide across separate table requests, as decide_event_status does for US7.1.

CREATE TABLE IF NOT EXISTS public.event_change_requests (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
    changed_field VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    -- US5.2's rule, decided when the request is made: 'important' or 'routine'.
    change_type VARCHAR(20) NOT NULL,
    requested_by_user_id INTEGER NOT NULL REFERENCES public.users(id),
    requested_at TIMESTAMP DEFAULT NOW() NOT NULL,
    -- The request's lifecycle. Answered rows are kept as the record of what
    -- was asked; only pending rows are shown for review.
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    CONSTRAINT event_change_requests_status_valid
        CHECK (status IN ('pending', 'approved', 'rejected')),
    CONSTRAINT event_change_requests_change_type_valid
        CHECK (change_type IN ('important', 'routine'))
);

-- The Coordinator's answer. Added separately so a table created from an
-- earlier draft of this script gains them too.
ALTER TABLE public.event_change_requests
    ADD COLUMN IF NOT EXISTS reviewed_by_user_id INTEGER REFERENCES public.users(id);
ALTER TABLE public.event_change_requests
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP;
-- The rejection reason the Organiser reads. Empty for an approval.
ALTER TABLE public.event_change_requests
    ADD COLUMN IF NOT EXISTS review_note TEXT;

-- The review panel and the Coordinator's queue both look up rows by event.
CREATE INDEX IF NOT EXISTS ix_event_change_requests_event_status
    ON public.event_change_requests (event_id, status);
CREATE INDEX IF NOT EXISTS ix_event_change_requests_requested_by
    ON public.event_change_requests (requested_by_user_id);
CREATE INDEX IF NOT EXISTS ix_event_change_requests_reviewed_by
    ON public.event_change_requests (reviewed_by_user_id);

-- Same server-only access path as every other table (see SUPABASE_HARDENING.sql).
ALTER TABLE public.event_change_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.event_change_requests FROM anon, authenticated;


CREATE OR REPLACE FUNCTION public.submit_change_request(
    p_event_id INTEGER,
    p_expected_status public.event_status,
    p_changed_by_id INTEGER,
    p_changes JSONB,
    p_notes TEXT DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    request_at TIMESTAMP := NOW();
    current_status public.event_status;
BEGIN
    -- Lock the event so a concurrent request or decision waits for this one,
    -- then check what the route checked: the same status, nothing pending.
    SELECT status INTO current_status
    FROM public.events
    WHERE id = p_event_id
    FOR UPDATE;

    IF NOT FOUND OR current_status <> p_expected_status THEN
        RETURN FALSE;
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.event_change_requests
        WHERE event_id = p_event_id AND status = 'pending'
    ) THEN
        RETURN FALSE;
    END IF;

    UPDATE public.events
    SET status = 'Under Review',
        updated_at = request_at
    WHERE id = p_event_id;

    INSERT INTO public.event_change_requests (
        event_id,
        changed_field,
        old_value,
        new_value,
        change_type,
        requested_by_user_id,
        requested_at
    )
    SELECT
        p_event_id,
        change ->> 'changed_field',
        change ->> 'old_value',
        change ->> 'new_value',
        change ->> 'change_type',
        p_changed_by_id,
        request_at
    FROM jsonb_array_elements(p_changes) AS change;

    INSERT INTO public.status_changes (
        event_id,
        old_status,
        new_status,
        changed_by_id,
        changed_at,
        notes
    )
    VALUES (
        p_event_id,
        p_expected_status,
        'Under Review',
        p_changed_by_id,
        request_at,
        p_notes
    );

    RETURN TRUE;
END;
$$;


CREATE OR REPLACE FUNCTION public.resolve_change_request(
    p_event_id INTEGER,
    p_approve BOOLEAN,
    p_changed_by_id INTEGER,
    p_notes TEXT DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    review_at TIMESTAMP := NOW();
    current_status public.event_status;
    proposed RECORD;
BEGIN
    -- Lock first, so two Coordinators cannot both answer the same request.
    SELECT status INTO current_status
    FROM public.events
    WHERE id = p_event_id
    FOR UPDATE;

    IF NOT FOUND OR current_status <> 'Under Review' THEN
        RETURN FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.event_change_requests
        WHERE event_id = p_event_id AND status = 'pending'
    ) THEN
        RETURN FALSE;
    END IF;

    IF p_approve THEN
        FOR proposed IN
            SELECT changed_field, old_value, new_value, change_type
            FROM public.event_change_requests
            WHERE event_id = p_event_id
              AND status = 'pending'
        LOOP
            -- One branch per column, so a value is only ever cast to the type of
            -- the column it was proposed for. Empty text means "not set": a
            -- cleared end date or attendance becomes NULL, as the backend writes
            -- those columns elsewhere.
            IF proposed.changed_field = 'name' THEN
                UPDATE public.events SET name = COALESCE(proposed.new_value, '')
                WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'purpose' THEN
                UPDATE public.events SET purpose = NULLIF(proposed.new_value, '')
                WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'description' THEN
                UPDATE public.events SET description = proposed.new_value
                WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'proposed_date' THEN
                UPDATE public.events SET proposed_date = NULLIF(proposed.new_value, '')::TIMESTAMP
                WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'end_date' THEN
                UPDATE public.events SET end_date = NULLIF(proposed.new_value, '')::TIMESTAMP
                WHERE id = p_event_id;
            ELSIF proposed.changed_field = 'expected_attendance' THEN
                UPDATE public.events
                SET expected_attendance = NULLIF(proposed.new_value, '')::INTEGER
                WHERE id = p_event_id;
            END IF;

            -- Now it is a change, so it is logged as one: the same row US5.2
            -- writes for a direct edit. The approving Coordinator is recorded
            -- as the one who changed the event; the Organiser who asked is on
            -- the request row.
            INSERT INTO public.event_changes (
                event_id,
                changed_field,
                old_value,
                new_value,
                change_type,
                changed_by_user_id,
                changed_at
            )
            VALUES (
                p_event_id,
                proposed.changed_field,
                proposed.old_value,
                proposed.new_value,
                proposed.change_type,
                p_changed_by_id,
                review_at
            );
        END LOOP;
    END IF;

    UPDATE public.event_change_requests
    SET status = CASE WHEN p_approve THEN 'approved' ELSE 'rejected' END,
        reviewed_by_user_id = p_changed_by_id,
        reviewed_at = review_at,
        review_note = p_notes
    WHERE event_id = p_event_id
      AND status = 'pending';

    -- The status stays Under Review, but the event did change: moving
    -- updated_at puts it back at the top of the Organiser's list.
    UPDATE public.events
    SET updated_at = review_at
    WHERE id = p_event_id;

    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.submit_change_request(
    INTEGER, public.event_status, INTEGER, JSONB, TEXT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.submit_change_request(
    INTEGER, public.event_status, INTEGER, JSONB, TEXT
) TO service_role;

REVOKE ALL ON FUNCTION public.resolve_change_request(
    INTEGER, BOOLEAN, INTEGER, TEXT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.resolve_change_request(
    INTEGER, BOOLEAN, INTEGER, TEXT
) TO service_role;


-- ---------------------------------------------------------------------------
-- OPTIONAL CLEANUP - only for a project that ran an EARLIER draft of this
-- script. Those drafts added columns to other tables that are no longer used.
-- Nothing reads them, so leaving them is harmless; remove them if you want the
-- schema tidy. Running this script has already replaced the functions that
-- wrote to them. Check each before uncommenting.
--
-- Draft 2 added these two columns:
-- ALTER TABLE public.events DROP COLUMN IF EXISTS change_requested;
-- ALTER TABLE public.status_changes DROP COLUMN IF EXISTS kind;
--
-- Draft 1 kept pending requests in event_changes. Look before deleting:
-- SELECT * FROM public.event_changes WHERE request_status IN ('pending', 'rejected');
-- DELETE FROM public.event_changes WHERE request_status IN ('pending', 'rejected');
-- ALTER TABLE public.event_changes DROP CONSTRAINT IF EXISTS event_changes_request_status_valid;
-- DROP INDEX IF EXISTS public.ix_event_changes_event_request_status;
-- ALTER TABLE public.event_changes DROP COLUMN IF EXISTS request_status;
-- ---------------------------------------------------------------------------
