-- US8.1 AC5: Backfill coordinator assignments for existing Submitted+ events
-- Apply after SUPABASE_ADD_COORDINATOR_ASSIGNMENT.sql
-- Safe to run repeatedly: only updates events where coordinator_id IS NULL.

-- Backfill coordinator assignments for all events that are Submitted or later
-- and don't have a coordinator assigned yet.
DO $$
DECLARE
    event_record RECORD;
    assigned_coordinator_id INT;
BEGIN
    -- Process events in order of submission (oldest first) to maintain round-robin fairness
    FOR event_record IN
        SELECT id
        FROM public.events
        WHERE status IN ('Submitted', 'Under Review', 'Approved', 'Planning', 'Confirmed', 'Completed')
          AND coordinator_id IS NULL
        ORDER BY submitted_at ASC NULLS LAST, created_at ASC
    LOOP
        -- Pick the next coordinator using the same round-robin logic
        assigned_coordinator_id := public.pick_next_coordinator();

        -- Assign the coordinator (NULL if no coordinators exist)
        UPDATE public.events
        SET coordinator_id = assigned_coordinator_id
        WHERE id = event_record.id;
    END LOOP;
END;
$$;
