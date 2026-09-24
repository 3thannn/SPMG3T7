-- Apply once to an existing Supabase project so events can be deleted.
-- status_changes is the audit trail for a single event, so the history goes
-- with the event rather than blocking the delete.
-- Safe to run repeatedly: dropping an absent constraint is a no-op.
ALTER TABLE public.status_changes
DROP CONSTRAINT IF EXISTS status_changes_event_id_fkey;

ALTER TABLE public.status_changes
ADD CONSTRAINT status_changes_event_id_fkey
FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE CASCADE;
