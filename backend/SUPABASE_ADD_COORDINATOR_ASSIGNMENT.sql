-- US8.1: Add coordinator_id column and round-robin assignment function
-- Apply once to an existing Supabase project before deploying US8.1.
-- Safe to run repeatedly: PostgreSQL treats IF NOT EXISTS and OR REPLACE as idempotent.

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

-- Create function to pick next coordinator via round-robin
-- This function is stateless and deterministic: it picks the coordinator
-- with the fewest assigned Submitted+ events, breaking ties by ID (lowest first).
CREATE OR REPLACE FUNCTION public.pick_next_coordinator()
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    next_coordinator_id INT;
BEGIN
    -- Find the coordinator with the fewest assigned events that are Submitted or later
    -- (Draft events are not assigned, and Rejected/Cancelled events free up capacity).
    -- Break ties by picking the lowest ID (deterministic round-robin).
    SELECT u.id INTO next_coordinator_id
    FROM public.users u
    WHERE u.role = 'Event Coordinator'
    ORDER BY (
        SELECT COUNT(*)
        FROM public.events e
        WHERE e.coordinator_id = u.id
          AND e.status NOT IN ('Draft', 'Rejected', 'Cancelled')
    ), u.id
    LIMIT 1;

    RETURN next_coordinator_id;
END;
$$;
