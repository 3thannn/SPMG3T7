-- US19.3. Apply after US17.2, US20.1 and US4.6 migrations, before the API deploy.
-- Planned times remain naive SGT; recorded times remain naive UTC.
BEGIN;
ALTER TABLE public.equipment_requests ADD COLUMN IF NOT EXISTS equipment_id INTEGER
    REFERENCES public.equipment(id) ON DELETE RESTRICT;
ALTER TABLE public.equipment_requests ADD COLUMN IF NOT EXISTS unavailable_reason TEXT
    NOT NULL DEFAULT '';
ALTER TABLE public.equipment_requests DROP CONSTRAINT IF EXISTS equipment_requests_status_valid;
ALTER TABLE public.equipment_requests ADD CONSTRAINT equipment_requests_status_valid
    CHECK (status IN ('Requested', 'Reserved', 'Unavailable', 'Removed'));
ALTER TABLE public.equipment_requests DROP CONSTRAINT IF EXISTS equipment_decision_valid;
ALTER TABLE public.equipment_requests ADD CONSTRAINT equipment_decision_valid CHECK (
    (status <> 'Reserved' OR equipment_id IS NOT NULL)
    AND (status <> 'Unavailable' OR btrim(unavailable_reason) <> '')
);
ALTER TABLE public.equipment_request_history ALTER COLUMN changed_at SET DEFAULT timezone('UTC', now());
CREATE INDEX IF NOT EXISTS ix_equipment_reservations
    ON public.equipment_requests(equipment_id, start_at, end_at) WHERE status = 'Reserved';

-- Extend the latest constraint rather than overwriting teammates' notice kinds.
DO $$ DECLARE definition TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
    WHERE conrelid = 'public.notifications'::regclass AND conname = 'notifications_kind_valid';
    IF definition NOT LIKE '%equipment-reserved%' THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7) || ') OR (kind IN '
            || '(''equipment-reserved'', ''equipment-unavailable'') AND status IS NULL '
            || 'AND equipment_request_id IS NULL))';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.equipment_request_snapshot(p_row public.equipment_requests)
RETURNS JSONB LANGUAGE SQL IMMUTABLE AS $$
    SELECT jsonb_build_object('equipment_type', (p_row).equipment_type,
        'quantity', (p_row).quantity, 'technical_requirements', (p_row).technical_requirements,
        'support_notes', (p_row).support_notes, 'start_at', (p_row).start_at,
        'end_at', (p_row).end_at, 'status', (p_row).status,
        'equipment_id', (p_row).equipment_id, 'unavailable_reason', (p_row).unavailable_reason);
$$;

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
    JOIN equipment e ON lower(e.equipment_type) = lower(q.equipment_type)
    CROSS JOIN LATERAL (
        SELECT coalesce(sum(r.quantity), 0)::BIGINT AS quantity
        FROM equipment_requests r WHERE r.equipment_id = e.id AND r.status = 'Reserved'
            AND r.start_at < q.end_at AND r.end_at > q.start_at
    ) used
    WHERE q.id = p_request_id ORDER BY lower(e.name), e.id;
$$;

CREATE OR REPLACE FUNCTION public.decide_equipment_request(
    p_request_id INTEGER, p_version INTEGER, p_actor_id INTEGER,
    p_equipment_id INTEGER DEFAULT NULL, p_reason TEXT DEFAULT '')
RETURNS JSONB LANGUAGE plpgsql SET search_path = public AS $$
DECLARE q equipment_requests%ROWTYPE; ev events%ROWTYPE; stock RECORD;
    decision TEXT; recorded TIMESTAMP := timezone('UTC', clock_timestamp());
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE id = p_actor_id AND role::TEXT = 'Technical Support') THEN
        RETURN jsonb_build_object('code', 'forbidden');
    END IF;
    -- Same line -> event lock order as existing edits/cancellation. Stock is
    -- locked last; never lock another reservation while holding stock.
    SELECT * INTO q FROM equipment_requests WHERE id = p_request_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('code', 'request_not_found'); END IF;
    IF q.version <> p_version OR q.status <> 'Requested' THEN
        RETURN jsonb_build_object('code', 'stale_request');
    END IF;
    SELECT * INTO ev FROM events WHERE id = q.event_id FOR UPDATE;
    IF ev.status::TEXT <> 'Planning' THEN RETURN jsonb_build_object('code', 'rule_refused'); END IF;
    IF p_equipment_id IS NOT NULL THEN
        PERFORM 1 FROM equipment WHERE id = p_equipment_id FOR UPDATE;
        SELECT * INTO stock FROM equipment_availability(q.id)
            WHERE "equipmentId" = p_equipment_id::TEXT;
        IF NOT FOUND THEN RETURN jsonb_build_object('code', 'invalid_equipment'); END IF;
        IF stock.shortfall > 0 THEN
            RETURN to_jsonb(stock) || jsonb_build_object('code', 'insufficient_stock');
        END IF;
        decision := 'Reserved';
    ELSE
        IF btrim(coalesce(p_reason, '')) = '' THEN
            RETURN jsonb_build_object('code', 'invalid_reason');
        END IF;
        decision := 'Unavailable';
    END IF;
    UPDATE equipment_requests SET status = decision, equipment_id = p_equipment_id,
        unavailable_reason = CASE WHEN decision = 'Unavailable' THEN btrim(p_reason) ELSE '' END,
        version = version + 1, updated_by_id = p_actor_id, updated_at = recorded WHERE id = q.id;
    IF ev.coordinator_id IS NOT NULL THEN
        INSERT INTO notifications(user_id, event_id, kind, status, message, created_at)
        VALUES (ev.coordinator_id, ev.id, 'equipment-' || lower(decision), NULL,
            q.quantity || ' × ' || q.equipment_type || ' for "' || ev.name || '": ' || decision || '.'
            || CASE WHEN decision = 'Unavailable' THEN ' Reason: ' || btrim(p_reason) ELSE '' END,
            recorded);
    END IF;
    RETURN jsonb_build_object('code', 'ok');
END $$;

-- Catalogue writes already hold the stock row lock. They must not invalidate
-- accepted promises. Check peak demand, allowing adjacent reservations.
CREATE OR REPLACE FUNCTION public.guard_reserved_equipment_stock()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public AS $$
DECLARE peak BIGINT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF EXISTS (SELECT 1 FROM equipment_requests WHERE equipment_id = OLD.id AND status = 'Reserved') THEN
            RAISE EXCEPTION 'Equipment has active reservations';
        END IF;
        RETURN OLD;
    END IF;
    IF NEW.equipment_type IS DISTINCT FROM OLD.equipment_type AND EXISTS (
        SELECT 1 FROM equipment_requests WHERE equipment_id = OLD.id AND status = 'Reserved') THEN
        RAISE EXCEPTION 'Equipment has active reservations';
    END IF;
    SELECT coalesce(max(demand), 0) INTO peak FROM (
        SELECT sum(delta) OVER (ORDER BY at) AS demand FROM (
            SELECT at, sum(delta) AS delta FROM (
                SELECT start_at AS at, quantity::BIGINT AS delta FROM equipment_requests
                    WHERE equipment_id = OLD.id AND status = 'Reserved'
                UNION ALL
                SELECT end_at, -quantity::BIGINT FROM equipment_requests
                    WHERE equipment_id = OLD.id AND status = 'Reserved'
            ) points GROUP BY at
        ) changes
    ) totals;
    IF NEW.total_quantity::BIGINT - NEW.out_of_service_quantity < peak THEN
        RAISE EXCEPTION 'Equipment has active reservations';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS guard_reserved_equipment_stock ON public.equipment;
CREATE TRIGGER guard_reserved_equipment_stock BEFORE UPDATE OR DELETE ON public.equipment
    FOR EACH ROW EXECUTE FUNCTION public.guard_reserved_equipment_stock();

REVOKE ALL ON FUNCTION public.equipment_availability(INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.decide_equipment_request(INTEGER, INTEGER, INTEGER, INTEGER, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.equipment_availability(INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.decide_equipment_request(INTEGER, INTEGER, INTEGER, INTEGER, TEXT)
    TO service_role;
COMMIT;
NOTIFY pgrst, 'reload schema';
