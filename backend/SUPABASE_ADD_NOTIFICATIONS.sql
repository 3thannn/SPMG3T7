-- US10.1: in-app notifications for an Organiser when their event's status changes.
-- Apply once to an existing Supabase project before deploying the
-- /notifications routes. Safe to run repeatedly: every statement is
-- IF NOT EXISTS or otherwise idempotent.
--
-- One row per notice, written by the backend when a Coordinator moves an event
-- to Under Review, Approved or Rejected. No email or push yet; the row is the
-- whole delivery.
CREATE TABLE IF NOT EXISTS public.notifications (
    id SERIAL PRIMARY KEY,
    -- Who it is for. A notice means nothing once its reader is gone.
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    -- What it is about. CASCADE so a removed event takes its notices with it.
    event_id INTEGER NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
    -- The status the event moved to, kept so the list can label a notice
    -- without re-reading the event, which may have moved on since.
    status public.event_status NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    -- When it was last marked read; NULL while unread.
    read_at TIMESTAMP
);

-- The one read path: a user's notices, unread first, newest first.
CREATE INDEX IF NOT EXISTS ix_notifications_user_read_created
    ON public.notifications (user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_notifications_event_id
    ON public.notifications (event_id);

-- Server-only access, as for every other table (see SUPABASE_HARDENING.sql).
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.notifications FROM anon, authenticated;

-- Verify the table is there with the expected columns.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'notifications'
ORDER BY ordinal_position;
