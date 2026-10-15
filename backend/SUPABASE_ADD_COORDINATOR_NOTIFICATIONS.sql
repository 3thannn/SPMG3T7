-- US10.2: in-app notifications for the Coordinator an event is assigned to.
-- Apply after SUPABASE_ADD_NOTIFICATIONS.sql and SUPABASE_ADD_EQUIPMENT_REQUESTS.sql.
-- Safe to run repeatedly: the constraint is dropped and re-added as a whole.
--
-- No new table and no new column. `user_id` is already the recipient, so a
-- Coordinator's notices share the table, list and read toggle with US10.1.
-- What changes is which `kind` a row may have. These notices are about an
-- event, not a status change, so like equipment requests they carry no status.
--
--   assigned          US8.3/US8.4  the event was assigned to them
--   unassigned        US8.4        the event was reassigned away from them
--   hold-expiring     US14.4       a tentative hold is about to expire
--   hold-expired      US14.4       a tentative hold has expired
--   booking-conflict  US12.2/15.2  venue unavailability or a setup change hit a booking
--   safety-changes    US17.2       the Safety Officer requested changes
BEGIN;

ALTER TABLE public.notifications DROP CONSTRAINT IF EXISTS notifications_kind_valid;
ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_valid CHECK (
    (kind = 'event-status' AND status IS NOT NULL AND equipment_request_id IS NULL)
    OR (kind = 'equipment-request' AND status IS NULL)
    OR (
        kind IN (
            'assigned',
            'unassigned',
            'hold-expiring',
            'hold-expired',
            'booking-conflict',
            'safety-changes'
        )
        AND status IS NULL
        AND equipment_request_id IS NULL
    )
);

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Verify the constraint now lists the US10.2 kinds.
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'notifications_kind_valid';
