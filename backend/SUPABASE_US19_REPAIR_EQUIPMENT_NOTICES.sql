-- US19: restore equipment notice kinds after another migration replaced the
-- notifications constraint. Preserve every kind already accepted by this DB.
-- Run this entire file in Supabase SQL Editor. Safe to run repeatedly.
BEGIN;
DO $$
DECLARE definition TEXT;
BEGIN
    -- Serialize constraint inspection/replacement with concurrent schema edits.
    LOCK TABLE public.notifications IN ACCESS EXCLUSIVE MODE;
    SELECT pg_get_constraintdef(oid) INTO definition
    FROM pg_constraint WHERE conrelid = 'public.notifications'::regclass
        AND conname = 'notifications_kind_valid';
    IF definition IS NULL THEN
        RAISE EXCEPTION 'Expected notifications_kind_valid constraint is missing';
    END IF;
    IF definition NOT LIKE '%equipment-reserved%'
        OR definition NOT LIKE '%equipment-unavailable%' THEN
        ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_valid;
        EXECUTE 'ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (('
            || substring(definition FROM 7) || ') OR (kind IN '
            || '(''equipment-reserved'', ''equipment-unavailable'') AND status IS NULL '
            || 'AND equipment_request_id IS NULL))';
    END IF;
END $$;
COMMIT;
NOTIFY pgrst, 'reload schema';
