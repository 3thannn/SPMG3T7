-- Apply after SUPABASE_US19_3_EQUIPMENT_RESERVATIONS.sql, before deploying.
-- Old type-only requests remain readable. A Coordinator must choose an item
-- when revising them. Existing reservations retain their stock linkage.
BEGIN;
ALTER TABLE public.equipment_requests ADD COLUMN IF NOT EXISTS requested_equipment_id INTEGER
    REFERENCES public.equipment(id) ON DELETE RESTRICT;
-- Metadata-only backfill, including reservations on events past Planning and
-- Removed lines on Cancelled events. ALTER TABLE holds its lock until COMMIT,
-- so application writes cannot slip through while these two triggers are off.
-- Do not manufacture user-edit/removal history for this schema migration.
-- All constraints and other triggers remain enabled. A failure rolls back both
-- the data update and the trigger changes; never run just this fragment.
ALTER TABLE public.equipment_requests DISABLE TRIGGER require_planning_for_equipment_request;
ALTER TABLE public.equipment_requests DISABLE TRIGGER record_equipment_request_history;
UPDATE public.equipment_requests SET requested_equipment_id = equipment_id
    WHERE requested_equipment_id IS NULL AND equipment_id IS NOT NULL;
ALTER TABLE public.equipment_requests ENABLE TRIGGER record_equipment_request_history;
ALTER TABLE public.equipment_requests ENABLE TRIGGER require_planning_for_equipment_request;
CREATE INDEX IF NOT EXISTS ix_equipment_requested_item
    ON public.equipment_requests(requested_equipment_id);

CREATE OR REPLACE FUNCTION public.guard_requested_equipment_type()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    IF NEW.equipment_type IS DISTINCT FROM OLD.equipment_type AND EXISTS (
        SELECT 1 FROM equipment_requests WHERE requested_equipment_id = OLD.id
            AND status IN ('Requested', 'Unavailable')) THEN
        RAISE EXCEPTION 'Equipment has active reservations';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS guard_requested_equipment_type ON public.equipment;
CREATE TRIGGER guard_requested_equipment_type BEFORE UPDATE ON public.equipment
    FOR EACH ROW EXECUTE FUNCTION public.guard_requested_equipment_type();

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
        FROM equipment_requests r WHERE r.equipment_id = e.id AND r.status = 'Reserved'
            AND r.start_at < q.end_at AND r.end_at > q.start_at
    ) used
    WHERE q.id = p_request_id;
$$;
-- Existing decision RPC only accepts items returned by equipment_availability:
-- this prevents substitution, including for legacy requests without an item.
CREATE OR REPLACE FUNCTION public.equipment_request_snapshot(p_row public.equipment_requests)
RETURNS JSONB LANGUAGE SQL IMMUTABLE AS $$
    SELECT jsonb_build_object('equipment_type', (p_row).equipment_type,
        'quantity', (p_row).quantity, 'technical_requirements', (p_row).technical_requirements,
        'support_notes', (p_row).support_notes, 'start_at', (p_row).start_at,
        'end_at', (p_row).end_at, 'status', (p_row).status,
        'equipment_id', (p_row).equipment_id, 'unavailable_reason', (p_row).unavailable_reason,
        'requested_equipment_id', (p_row).requested_equipment_id);
$$;
COMMIT;
NOTIFY pgrst, 'reload schema';
