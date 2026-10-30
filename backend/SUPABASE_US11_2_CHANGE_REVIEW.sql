BEGIN;

-- Apply after US2.1 event needs, US11.1, lifecycle and US19.3 migrations.
-- Idempotent. Planned timestamps remain SGT; recorded timestamps remain UTC.
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS review_state JSONB NOT NULL DEFAULT '{}';
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS arrangement_review_pending BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS arrangement_review JSONB NOT NULL DEFAULT '[]';
ALTER TABLE public.venue_bookings ADD COLUMN IF NOT EXISTS event_conflict_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE public.venue_bookings ADD COLUMN IF NOT EXISTS event_conflict_at TIMESTAMP;
ALTER TABLE public.equipment_requests ADD COLUMN IF NOT EXISTS event_conflict_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE public.equipment_requests ADD COLUMN IF NOT EXISTS event_conflict_at TIMESTAMP;
ALTER TABLE public.event_change_requests DROP CONSTRAINT IF EXISTS event_change_requests_status_valid;
ALTER TABLE public.event_change_requests ADD CONSTRAINT event_change_requests_status_valid
    CHECK (status IN ('pending','approved','rejected','superseded'));

DO $$ DECLARE definition TEXT; BEGIN
    SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
    WHERE conrelid='public.notifications'::regclass AND conname='notifications_kind_valid';
    IF definition NOT LIKE '%clarification-requested%' THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7) || ') OR (kind IN (''change-submitted'', ''arrangement-conflict'',
            ''change-accepted'', ''change-rejected'', ''clarification-requested'')'
            || ' AND status IS NULL AND equipment_request_id IS NULL))';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.us11_apply(p_event_id INTEGER, p_actor_id INTEGER, p_changes JSONB)
RETURNS VOID LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE c JSONB; col TEXT; current_value TEXT; value TEXT; kind public.change_type;
BEGIN
    FOR c IN SELECT * FROM jsonb_array_elements(p_changes) LOOP
        col := c->>'changed_field';
        IF col NOT IN ('name','purpose','description','proposed_date','end_date','expected_attendance',
                      'venue_requirements','preferred_layout','accessibility_needs','equipment_needs','registration_needs')
        THEN RAISE EXCEPTION 'Unknown event field'; END IF;
        EXECUTE format('SELECT %I::TEXT FROM public.events WHERE id=$1',col)
            INTO current_value USING p_event_id;
        value := c->>'new_value';
        kind := CASE WHEN col IN ('proposed_date','end_date','expected_attendance','venue_requirements',
            'preferred_layout','accessibility_needs','equipment_needs') THEN 'important'::public.change_type
            ELSE 'routine'::public.change_type END;
        IF col IN ('proposed_date','end_date') THEN
            EXECUTE format('UPDATE public.events SET %I=NULLIF($1,'''')::TIMESTAMP WHERE id=$2', col)
                USING value,p_event_id;
        ELSIF col='expected_attendance' THEN
            UPDATE public.events SET expected_attendance=NULLIF(value,'')::INTEGER WHERE id=p_event_id;
        ELSE
            EXECUTE format('UPDATE public.events SET %I=$1 WHERE id=$2', col) USING value,p_event_id;
        END IF;
        INSERT INTO public.event_changes(event_id,changed_field,old_value,new_value,change_type,changed_by_user_id,changed_at)
            VALUES(p_event_id,col,current_value,value,kind,p_actor_id,timezone('UTC',clock_timestamp()));
        IF col IN ('proposed_date','end_date','expected_attendance') THEN
            UPDATE public.events SET arrangement_review_pending=TRUE WHERE id=p_event_id;
        END IF;
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION public.us11_review(p_event_id INTEGER,p_actor_id INTEGER,p_action TEXT,
                                             p_revision INTEGER,p_payload JSONB)
RETURNS BOOLEAN LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE e public.events; state JSONB; at_time TIMESTAMP := timezone('UTC',clock_timestamp());
        c JSONB; entry JSONB; answer TEXT; field_name TEXT; current_value TEXT;
        pending BOOLEAN; awaiting BOOLEAN;
BEGIN
    SELECT * INTO e FROM public.events WHERE id=p_event_id FOR UPDATE;
    IF NOT FOUND OR coalesce((e.review_state->>'revision')::INTEGER,0)<>p_revision
        OR e.status IN ('Draft','Completed','Cancelled','Rejected') THEN RETURN FALSE; END IF;
    state := e.review_state;
    awaiting := coalesce((state->>'awaitingReply')::BOOLEAN,FALSE);
    SELECT EXISTS(SELECT 1 FROM public.event_change_requests WHERE event_id=p_event_id AND status='pending') INTO pending;
    IF p_action='submit' THEN
        IF e.organiser_id<>p_actor_id OR (e.status='Under Review' AND NOT awaiting)
            OR (pending AND NOT awaiting) OR jsonb_array_length(p_payload->'changes')=0 THEN RETURN FALSE; END IF;
        UPDATE public.event_change_requests SET status='superseded',reviewed_at=at_time
            WHERE event_id=p_event_id AND status='pending';
        INSERT INTO public.event_change_requests(event_id,changed_field,old_value,new_value,change_type,
            requested_by_user_id,requested_at,request_note)
        SELECT p_event_id,proposed_change.value->>'changed_field',proposed_change.value->>'old_value',
            proposed_change.value->>'new_value',proposed_change.value->>'change_type',
            p_actor_id,at_time,p_payload->>'note'
        FROM jsonb_array_elements(p_payload->'changes') AS proposed_change(value);
        entry := jsonb_build_object('kind','proposal','message',p_payload->>'note','changes',p_payload->'changes');
        state := state || jsonb_build_object('awaitingReply',FALSE);
    ELSE
        IF e.coordinator_id IS DISTINCT FROM p_actor_id THEN RETURN FALSE; END IF;
        IF p_action='clarify' THEN
            IF (e.status NOT IN ('Submitted','Under Review') AND NOT pending)
                OR length(btrim(coalesce(p_payload->>'message','')))=0
                OR length(p_payload->>'message')>2000 THEN RETURN FALSE; END IF;
            entry := jsonb_build_object('kind','clarification','message',p_payload->>'message');
            state := state || jsonb_build_object('awaitingReply',TRUE,'clarificationId',p_revision+1);
            INSERT INTO public.status_changes(event_id,old_status,new_status,changed_by_id,changed_at,notes)
                VALUES(p_event_id,e.status,e.status,p_actor_id,at_time,p_payload->>'message');
        ELSIF p_action IN ('approve','reject') THEN
            IF NOT pending THEN RETURN FALSE; END IF;
            IF p_action='reject' AND (length(btrim(coalesce(p_payload->>'note','')))=0
                OR length(p_payload->>'note')>2000) THEN RETURN FALSE; END IF;
            IF p_action='approve' THEN
                FOR c IN SELECT to_jsonb(r) FROM public.event_change_requests r
                    WHERE event_id=p_event_id AND status='pending' LOOP
                    field_name := c->>'changed_field';
                    IF field_name NOT IN ('name','purpose','description','proposed_date','end_date','expected_attendance',
                        'venue_requirements','preferred_layout','accessibility_needs','equipment_needs','registration_needs')
                    THEN RETURN FALSE; END IF;
                    EXECUTE format('SELECT %I::TEXT FROM public.events WHERE id=$1',field_name)
                        INTO current_value USING p_event_id;
                    IF field_name IN ('proposed_date','end_date') THEN
                        IF NULLIF(current_value,'')::TIMESTAMP IS DISTINCT FROM NULLIF(c->>'old_value','')::TIMESTAMP
                            THEN RETURN FALSE; END IF;
                    ELSIF coalesce(current_value,'')<>coalesce(c->>'old_value','') THEN RETURN FALSE; END IF;
                END LOOP;
                PERFORM public.us11_apply(p_event_id,p_actor_id,(SELECT jsonb_agg(to_jsonb(r))
                    FROM public.event_change_requests r WHERE event_id=p_event_id AND status='pending'));
            END IF;
            answer := CASE WHEN p_action='approve' THEN 'approved' ELSE 'rejected' END;
            UPDATE public.event_change_requests SET status=answer,reviewed_at=at_time,
                reviewed_by_user_id=p_actor_id,review_note=p_payload->>'note'
                WHERE event_id=p_event_id AND status='pending';
            entry := jsonb_build_object('kind',answer,'message',p_payload->>'note');
            state := state || jsonb_build_object('awaitingReply',FALSE);
        ELSE RETURN FALSE; END IF;
    END IF;
    entry := entry || jsonb_build_object('revision',p_revision+1,'byId',p_actor_id::TEXT,'byName',(SELECT name FROM public.users WHERE id=p_actor_id),'at',at_time,
                                        'clarificationId',state->'clarificationId');
    state := state || jsonb_build_object('revision',p_revision+1,
        'messages',coalesce(state->'messages','[]') || jsonb_build_array(entry));
    UPDATE public.events SET review_state=state,updated_at=at_time WHERE id=p_event_id;
    RETURN TRUE;
END $$;

CREATE OR REPLACE FUNCTION public.us11_edit(p_event_id INTEGER,p_actor_id INTEGER,
                                            p_updated_at TIMESTAMP,p_changes JSONB)
RETURNS BOOLEAN LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE e public.events;
BEGIN
    SELECT * INTO e FROM public.events WHERE id=p_event_id FOR UPDATE;
    IF NOT FOUND OR e.coordinator_id IS DISTINCT FROM p_actor_id OR e.updated_at<>p_updated_at
        OR e.status IN ('Draft','Completed','Cancelled','Rejected') OR EXISTS(
            SELECT 1 FROM public.event_change_requests WHERE event_id=p_event_id AND status='pending'
        ) THEN RETURN FALSE; END IF;
    PERFORM public.us11_apply(p_event_id,p_actor_id,p_changes);
    UPDATE public.events SET updated_at=timezone('UTC',clock_timestamp()) WHERE id=p_event_id;
    RETURN TRUE;
END $$;

REVOKE ALL ON FUNCTION public.us11_apply(INTEGER,INTEGER,JSONB) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.us11_review(INTEGER,INTEGER,TEXT,INTEGER,JSONB) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.us11_edit(INTEGER,INTEGER,TIMESTAMP,JSONB) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.us11_apply(INTEGER,INTEGER,JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.us11_review(INTEGER,INTEGER,TEXT,INTEGER,JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.us11_edit(INTEGER,INTEGER,TIMESTAMP,JSONB) TO service_role;


CREATE OR REPLACE FUNCTION public.equipment_availability(p_request_id INTEGER)
RETURNS TABLE ("equipmentId" TEXT, name TEXT, location TEXT, "totalQuantity" INTEGER,
    "outOfServiceQuantity" INTEGER, "reservedQuantity" BIGINT,
    "availableQuantity" BIGINT, shortfall BIGINT)
LANGUAGE SQL STABLE SET search_path = public AS $$
    SELECT e.id::TEXT, e.name::TEXT, e.location::TEXT, e.total_quantity,
        e.out_of_service_quantity, used.quantity,
        e.total_quantity::BIGINT - e.out_of_service_quantity - used.quantity,
        greatest(0::BIGINT, q.quantity -
            (e.total_quantity::BIGINT - e.out_of_service_quantity - used.quantity))
    FROM equipment_requests q
    JOIN equipment e ON e.id = q.requested_equipment_id
    CROSS JOIN LATERAL (
        SELECT coalesce(sum(r.quantity), 0)::BIGINT AS quantity
        FROM equipment_requests r WHERE r.equipment_id = e.id AND r.status = 'Reserved' AND r.id <> q.id
            AND r.start_at < q.end_at AND r.end_at > q.start_at
    ) used
    WHERE q.id = p_request_id;
$$;

-- Permit review metadata on Reserved lines after Planning without weakening
-- the existing guard on stock, quantities, status, or technical content.
DO $$ DECLARE definition TEXT; BEGIN
    SELECT pg_get_functiondef('public.require_planning_for_equipment_request()'::regprocedure)
        INTO definition;
    IF definition NOT LIKE '%event_conflict_reason%' THEN
        definition := replace(definition, 'BEGIN', $guard$BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF (to_jsonb(NEW) - 'event_conflict_reason' - 'event_conflict_at')
        = (to_jsonb(OLD) - 'event_conflict_reason' - 'event_conflict_at') THEN
      RETURN NEW;
    END IF;
  END IF;
$guard$);
        EXECUTE definition;
    END IF;
END $$;

-- Metadata checks do not constitute Technical Support edits in the audit trail.
DO $$ DECLARE definition TEXT; BEGIN
    SELECT pg_get_functiondef('public.record_equipment_request_history()'::regprocedure)
        INTO definition;
    IF definition NOT LIKE '%event_conflict_reason%' THEN
        definition := replace(definition, 'BEGIN', $guard$BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF (to_jsonb(NEW) - 'event_conflict_reason' - 'event_conflict_at')
        = (to_jsonb(OLD) - 'event_conflict_reason' - 'event_conflict_at') THEN
      RETURN NEW;
    END IF;
  END IF;
$guard$);
        EXECUTE definition;
    END IF;
END $$;

-- Checking flags is not an event content edit: keep the content version stable.
-- Use a dedicated event trigger so the shared users/venues/equipment trigger is unchanged.
CREATE OR REPLACE FUNCTION public.us11_event_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF (to_jsonb(NEW) - 'arrangement_review' - 'arrangement_review_pending') =
       (to_jsonb(OLD) - 'arrangement_review' - 'arrangement_review_pending') THEN
        NEW.updated_at := OLD.updated_at;
    ELSE
        NEW.updated_at := timezone('UTC',clock_timestamp());
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS update_events_updated_at ON public.events;
CREATE TRIGGER update_events_updated_at BEFORE UPDATE ON public.events
    FOR EACH ROW EXECUTE FUNCTION public.us11_event_updated_at();
REVOKE ALL ON FUNCTION public.us11_event_updated_at() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.us11_event_updated_at() TO service_role;
NOTIFY pgrst, 'reload schema';

COMMIT;
