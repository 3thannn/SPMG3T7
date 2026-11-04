-- US19.0-19.2. Apply after SUPABASE_ADD_NOTIFICATIONS.sql.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='equipment' AND column_name='quantity_available')
     AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='equipment' AND column_name='total_quantity') THEN
    ALTER TABLE public.equipment RENAME COLUMN quantity_available TO total_quantity;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='equipment' AND column_name='technical_specs')
     AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='equipment' AND column_name='description') THEN
    ALTER TABLE public.equipment RENAME COLUMN technical_specs TO description;
  END IF;
END $$;

ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT '';
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS out_of_service_quantity INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS out_of_service_reason TEXT NOT NULL DEFAULT '';
UPDATE public.equipment SET description = '' WHERE description IS NULL;
ALTER TABLE public.equipment ALTER COLUMN description SET DEFAULT '';
ALTER TABLE public.equipment ALTER COLUMN description SET NOT NULL;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'equipment_stock_valid') THEN
    ALTER TABLE public.equipment ADD CONSTRAINT equipment_stock_valid
      CHECK (total_quantity >= 0 AND out_of_service_quantity >= 0 AND out_of_service_quantity <= total_quantity
        AND (out_of_service_quantity = 0 OR length(trim(out_of_service_reason)) > 0));
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.equipment_requests (
  id SERIAL PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
  equipment_type VARCHAR(100) NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity >= 1),
  technical_requirements TEXT NOT NULL DEFAULT '',
  support_notes TEXT NOT NULL DEFAULT '',
  start_at TIMESTAMP NOT NULL,
  end_at TIMESTAMP NOT NULL,
  status TEXT NOT NULL DEFAULT 'Requested',
  requested_by_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
  updated_by_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  CONSTRAINT equipment_request_time_valid CHECK (start_at < end_at)
);
ALTER TABLE public.equipment_requests ADD COLUMN IF NOT EXISTS updated_by_id INTEGER
  REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE public.equipment_requests DROP CONSTRAINT IF EXISTS equipment_requests_status_check;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'equipment_requests_status_valid') THEN
    ALTER TABLE public.equipment_requests ADD CONSTRAINT equipment_requests_status_valid
      CHECK (status IN ('Requested', 'Removed'));
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_equipment_requests_queue
  ON public.equipment_requests(status, created_at, id);
CREATE INDEX IF NOT EXISTS ix_equipment_requests_event ON public.equipment_requests(event_id);
ALTER TABLE public.equipment_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.equipment_requests FROM anon, authenticated;

-- Triggered in the same transaction as a request write, including soft removal.
-- History survives removal and records the old and new values for each edit.
CREATE TABLE IF NOT EXISTS public.equipment_request_history (
  id BIGSERIAL PRIMARY KEY,
  request_id INTEGER NOT NULL,
  event_id INTEGER NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
  actor_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
  action TEXT NOT NULL CHECK (action IN ('Created', 'Updated', 'Removed')),
  changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
  before_data JSONB,
  after_data JSONB
);
CREATE INDEX IF NOT EXISTS ix_equipment_request_history_event
  ON public.equipment_request_history(event_id, changed_at DESC, id DESC);
ALTER TABLE public.equipment_request_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.equipment_request_history FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.equipment_request_snapshot(p_row public.equipment_requests)
RETURNS JSONB LANGUAGE SQL IMMUTABLE AS $$
  SELECT jsonb_build_object(
    'equipment_type', (p_row).equipment_type,
    'quantity', (p_row).quantity,
    'technical_requirements', (p_row).technical_requirements,
    'support_notes', (p_row).support_notes,
    'start_at', (p_row).start_at,
    'end_at', (p_row).end_at
  );
$$;
CREATE OR REPLACE FUNCTION public.record_equipment_request_history()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO public.equipment_request_history
      (request_id, event_id, actor_id, action, after_data)
    VALUES (NEW.id, NEW.event_id, NEW.requested_by_id, 'Created',
            public.equipment_request_snapshot(NEW));
  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO public.equipment_request_history
      (request_id, event_id, actor_id, action, before_data, after_data)
    VALUES (NEW.id, NEW.event_id, NEW.updated_by_id,
            CASE WHEN NEW.status = 'Removed' THEN 'Removed' ELSE 'Updated' END,
            public.equipment_request_snapshot(OLD),
            CASE WHEN NEW.status = 'Removed' THEN NULL
                 ELSE public.equipment_request_snapshot(NEW) END);
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS record_equipment_request_history ON public.equipment_requests;
CREATE TRIGGER record_equipment_request_history
AFTER INSERT OR UPDATE ON public.equipment_requests
FOR EACH ROW EXECUTE FUNCTION public.record_equipment_request_history();

-- Serialize request writes with event status changes. The API checks Planning
-- first for a clear error; this closes the race after that check.
CREATE OR REPLACE FUNCTION public.require_planning_for_equipment_request()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE current_status public.event_status;
BEGIN
  SELECT status INTO current_status FROM public.events WHERE id = NEW.event_id FOR UPDATE;
  IF current_status IS DISTINCT FROM 'Planning'::public.event_status THEN
    RAISE EXCEPTION 'Equipment requests can only change while the event is Planning';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS require_planning_for_equipment_request ON public.equipment_requests;
CREATE TRIGGER require_planning_for_equipment_request
BEFORE INSERT OR UPDATE ON public.equipment_requests
FOR EACH ROW EXECUTE FUNCTION public.require_planning_for_equipment_request();

-- A Requested line must be resolved by the later reservation flow before an
-- event can leave Planning. This also guards a future transition implemented
-- outside the current API.
CREATE OR REPLACE FUNCTION public.prevent_planning_exit_with_equipment_requests()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'Planning' AND NEW.status <> 'Planning'
     AND EXISTS (SELECT 1 FROM public.equipment_requests
                 WHERE event_id = OLD.id AND status = 'Requested') THEN
    RAISE EXCEPTION 'Resolve Requested equipment lines before leaving Planning';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS prevent_planning_exit_with_equipment_requests ON public.events;
CREATE TRIGGER prevent_planning_exit_with_equipment_requests
BEFORE UPDATE OF status ON public.events
FOR EACH ROW EXECUTE FUNCTION public.prevent_planning_exit_with_equipment_requests();

ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'event-status';
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS equipment_request_id INTEGER
  REFERENCES public.equipment_requests(id) ON DELETE SET NULL;
ALTER TABLE public.notifications ALTER COLUMN status DROP NOT NULL;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'notifications_kind_valid') THEN
    ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (
      (kind = 'event-status' AND status IS NOT NULL AND equipment_request_id IS NULL)
      OR (kind = 'equipment-request' AND status IS NULL)
    );
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_notifications_equipment_request
  ON public.notifications(equipment_request_id);

-- Earlier manual user inserts may have left the serial sequence behind.
SELECT setval(pg_get_serial_sequence('public.users', 'id'),
              GREATEST((SELECT COALESCE(MAX(id), 1) FROM public.users), 1));

INSERT INTO public.users (email, name, role)
VALUES ('technicalsupport@connectsphere.com', 'Bryan', 'Technical Support')
ON CONFLICT (email) DO NOTHING;

NOTIFY pgrst, 'reload schema';
