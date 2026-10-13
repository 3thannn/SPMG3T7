-- Add the coordinator_id column used by Lead assignment (US8.3).
-- Apply once to an existing Supabase project before deploying US8.1.
-- Safe to run repeatedly.

-- Add coordinator_id column to events table with foreign key to users
ALTER TABLE public.events
ADD COLUMN IF NOT EXISTS coordinator_id INT;

ALTER TABLE public.events
DROP CONSTRAINT IF EXISTS events_coordinator_id_fkey;

ALTER TABLE public.events
ADD CONSTRAINT events_coordinator_id_fkey
FOREIGN KEY (coordinator_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- Create index on coordinator_id for efficient filtering
CREATE INDEX IF NOT EXISTS idx_events_coordinator_id
ON public.events(coordinator_id);
