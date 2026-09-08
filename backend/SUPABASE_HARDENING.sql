-- ConnectSphere Sprint 1: safe follow-up for an existing SUPABASE_SETUP.sql database.
-- This is additive/idempotent: it does not drop, rename, or rewrite application data.
-- Run once in the Supabase SQL Editor using a project-owner connection.

-- Covers the status_changes.changed_by_id foreign key used when rendering audit history.
CREATE INDEX IF NOT EXISTS ix_status_changes_changed_by_id
    ON public.status_changes (changed_by_id);

-- Fix Supabase's mutable-search-path advisor finding. This trigger function does
-- not access any relation, so an empty search path is the safest setting.
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- The supported access path is browser -> FastAPI -> service-role Supabase client.
-- RLS stays enabled as defence in depth, and no browser-facing policies are added.
-- Revoking direct table privileges makes that server-only design explicit.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.status_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.venues ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.equipment ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.users, public.events, public.status_changes,
    public.venues, public.equipment FROM anon, authenticated;
