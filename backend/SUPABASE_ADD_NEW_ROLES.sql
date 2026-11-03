-- US1.4: Add Coordinator Lead and Safety Officer roles
-- Run this in Supabase SQL Editor: Dashboard → SQL Editor → New Query → Paste → Run

-- Step 1: Add new role values to the user_role enum
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Event Coordinator Lead';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Safety Officer';

-- Step 2: Insert users with the new roles into public.users
-- Note: You still need to create auth accounts separately (see instructions below)
INSERT INTO public.users (id, email, name, role, created_at, updated_at)
VALUES
    (3, 'coordinatorlead@connectsphere.com', 'Jordan', 'Event Coordinator Lead', NOW(), NOW()),
    (5, 'safetyofficer@connectsphere.com', 'Alex', 'Safety Officer', NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name,
    role = EXCLUDED.role,
    updated_at = NOW();

-- Verify the changes
SELECT id, email, name, role FROM public.users ORDER BY id;
