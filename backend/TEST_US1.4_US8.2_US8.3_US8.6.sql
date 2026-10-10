-- =============================================================================
-- COMPLETE TEST SETUP FOR US1.4, US8.2, US8.3, US8.6
-- =============================================================================
-- Run this in Supabase SQL Editor to test all 4 user stories
-- After running this, you'll still need to create Auth users manually
-- (instructions at the bottom)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- STEP 1: Add new roles to enum (US1.4)
-- -----------------------------------------------------------------------------
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Event Coordinator Lead';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Safety Officer';

-- -----------------------------------------------------------------------------
-- STEP 2: Create users for new roles (US1.4)
-- -----------------------------------------------------------------------------
-- Note: These are the public.users entries
-- You still need to create auth.users separately (see instructions below)

-- Coordinator Lead
INSERT INTO public.users (id, email, name, role, created_at, updated_at)
VALUES (3, 'coordinatorlead@spmg3t7.edu', 'Jordan', 'Event Coordinator Lead', NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name,
    role = EXCLUDED.role,
    updated_at = NOW();

-- Safety Officer
INSERT INTO public.users (id, email, name, role, created_at, updated_at)
VALUES (5, 'safetyofficer@spmg3t7.edu', 'Alex', 'Safety Officer', NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name,
    role = EXCLUDED.role,
    updated_at = NOW();

-- Additional Coordinator for testing US8.6 (visibility isolation)
INSERT INTO public.users (id, email, name, role, created_at, updated_at)
VALUES (10, 'coordinator2@spmg3t7.edu', 'Sam Chen', 'Event Coordinator', NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name,
    role = EXCLUDED.role,
    updated_at = NOW();

-- -----------------------------------------------------------------------------
-- STEP 3: Create test events for US8.2 (Unassigned Queue)
-- -----------------------------------------------------------------------------
-- These events will appear in the unassigned queue

-- Unassigned Event 1 (oldest)
INSERT INTO public.events (
    id, name, purpose, description, proposed_date, end_date, expected_attendance,
    status, organiser_id, coordinator_id, created_at, updated_at
)
VALUES (
    101,
    'Annual Tech Conference 2027',
    'Technology trends and networking',
    'A full-day conference featuring keynote speakers, workshops, and networking opportunities',
    '2027-03-15T09:00:00',
    '2027-03-15T18:00:00',
    200,
    'Submitted',
    1, -- Dylan (organiser)
    NULL, -- UNASSIGNED - will appear in queue
    '2027-02-01T10:00:00',
    '2027-02-01T10:00:00'
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    purpose = EXCLUDED.purpose,
    description = EXCLUDED.description,
    proposed_date = EXCLUDED.proposed_date,
    end_date = EXCLUDED.end_date,
    expected_attendance = EXCLUDED.expected_attendance,
    status = EXCLUDED.status,
    coordinator_id = EXCLUDED.coordinator_id,
    updated_at = NOW();

-- Unassigned Event 2 (middle)
INSERT INTO public.events (
    id, name, purpose, description, proposed_date, end_date, expected_attendance,
    status, organiser_id, coordinator_id, created_at, updated_at
)
VALUES (
    102,
    'Spring Networking Mixer',
    'Connect professionals across industries',
    'Casual networking event with refreshments',
    '2027-04-10T18:00:00',
    '2027-04-10T21:00:00',
    75,
    'Submitted',
    1, -- Dylan
    NULL, -- UNASSIGNED
    '2027-02-05T14:00:00',
    '2027-02-05T14:00:00'
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    purpose = EXCLUDED.purpose,
    status = EXCLUDED.status,
    coordinator_id = EXCLUDED.coordinator_id,
    updated_at = NOW();

-- Unassigned Event 3 (newest)
INSERT INTO public.events (
    id, name, purpose, description, proposed_date, end_date, expected_attendance,
    status, organiser_id, coordinator_id, created_at, updated_at
)
VALUES (
    103,
    'Career Fair 2027',
    'Connect students with employers',
    'Annual career fair with 50+ companies',
    '2027-05-20T10:00:00',
    '2027-05-20T16:00:00',
    500,
    'Submitted',
    1, -- Dylan
    NULL, -- UNASSIGNED
    '2027-02-10T09:00:00',
    '2027-02-10T09:00:00'
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    status = EXCLUDED.status,
    coordinator_id = EXCLUDED.coordinator_id,
    updated_at = NOW();

-- -----------------------------------------------------------------------------
-- STEP 4: Create events for US8.6 (Visibility Testing)
-- -----------------------------------------------------------------------------
-- Event assigned to Coordinator 1 (Priya, ID=2)
INSERT INTO public.events (
    id, name, purpose, description, proposed_date, end_date, expected_attendance,
    status, organiser_id, coordinator_id, created_at, updated_at
)
VALUES (
    104,
    'Workshop Series - Assigned to Priya',
    'Professional development workshops',
    'Monthly workshop series',
    '2027-06-01T14:00:00',
    '2027-06-01T17:00:00',
    30,
    'Submitted',
    1, -- Dylan
    2, -- ASSIGNED to Priya (coordinator@spmg3t7.edu)
    '2027-02-15T11:00:00',
    '2027-02-15T11:00:00'
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    coordinator_id = EXCLUDED.coordinator_id,
    updated_at = NOW();

-- Event assigned to Coordinator 2 (Sam, ID=10)
INSERT INTO public.events (
    id, name, purpose, description, proposed_date, end_date, expected_attendance,
    status, organiser_id, coordinator_id, created_at, updated_at
)
VALUES (
    105,
    'Training Seminar - Assigned to Sam',
    'Skills training for new staff',
    'Orientation and training',
    '2027-06-15T09:00:00',
    '2027-06-15T12:00:00',
    25,
    'Submitted',
    1, -- Dylan
    10, -- ASSIGNED to Sam (coordinator2@spmg3t7.edu)
    '2027-02-20T10:00:00',
    '2027-02-20T10:00:00'
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    coordinator_id = EXCLUDED.coordinator_id,
    updated_at = NOW();

-- -----------------------------------------------------------------------------
-- STEP 5: Add status change history for audit trail
-- -----------------------------------------------------------------------------
-- History for Event 101 (submitted)
-- Note: Skipping NULL → Draft since old_status is NOT NULL
INSERT INTO public.status_changes (event_id, old_status, new_status, changed_by_id, changed_at, notes)
VALUES (101, 'Draft', 'Submitted', 1, '2027-02-01T10:00:00', '')
ON CONFLICT DO NOTHING;

-- History for Event 104 (assigned event)
-- Note: Skipping NULL → Draft since old_status is NOT NULL
INSERT INTO public.status_changes (event_id, old_status, new_status, changed_by_id, changed_at, notes)
VALUES (104, 'Draft', 'Submitted', 1, '2027-02-15T11:00:00', '')
ON CONFLICT DO NOTHING;

-- -----------------------------------------------------------------------------
-- STEP 6: Verify the setup
-- -----------------------------------------------------------------------------
SELECT '=== NEW ROLES ===' as section;
SELECT id, email, name, role
FROM public.users
WHERE role IN ('Event Coordinator Lead', 'Safety Officer')
ORDER BY id;

SELECT '=== ALL COORDINATORS ===' as section;
SELECT id, email, name, role
FROM public.users
WHERE role = 'Event Coordinator' OR role = 'Event Coordinator Lead'
ORDER BY id;

SELECT '=== UNASSIGNED EVENTS (Should appear in queue) ===' as section;
SELECT id, name, expected_attendance, organiser_id, coordinator_id, status, created_at
FROM public.events
WHERE status = 'Submitted' AND coordinator_id IS NULL
ORDER BY created_at;

SELECT '=== ASSIGNED EVENTS (For visibility testing) ===' as section;
SELECT id, name, coordinator_id, status,
       (SELECT name FROM public.users WHERE id = events.coordinator_id) as assigned_to
FROM public.events
WHERE coordinator_id IS NOT NULL
ORDER BY id;

-- =============================================================================
-- MANUAL STEPS: Create Auth Users
-- =============================================================================
-- After running this SQL, go to Supabase Dashboard:
--
-- 1. Go to Authentication → Users → Add user
-- 2. Create these 3 auth accounts:
--
--    Account 1 (Coordinator Lead):
--    - Email: coordinatorlead@spmg3t7.edu
--    - Password: Sprint1!demo
--    - ✅ Auto Confirm User
--
--    Account 2 (Safety Officer):
--    - Email: safetyofficer@spmg3t7.edu
--    - Password: Sprint1!demo
--    - ✅ Auto Confirm User
--
--    Account 3 (Second Coordinator):
--    - Email: coordinator2@spmg3t7.edu
--    - Password: Sprint1!demo
--    - ✅ Auto Confirm User
--
-- =============================================================================
-- TEST SCENARIOS
-- =============================================================================
--
-- ✅ US1.4 - New Roles Route to Home:
--    1. Sign in as coordinatorlead@spmg3t7.edu
--    2. Should redirect to /unassigned-queue
--    3. Sign in as safetyofficer@spmg3t7.edu
--    4. Should redirect to /safety-review
--
-- ✅ US8.2 - Unassigned Queue:
--    1. Sign in as Coordinator Lead
--    2. Should see 3 events in unassigned queue
--    3. Oldest first: "Annual Tech Conference 2027"
--    4. Regular coordinator should NOT see /unassigned-queue (403)
--
-- ✅ US8.3 - Lead Assigns Coordinator:
--    1. Sign in as Coordinator Lead
--    2. Click "Assign Coordinator" on "Annual Tech Conference 2027"
--    3. See Priya and Sam in the picker
--    4. Assign to Priya
--    5. Event should disappear from queue
--    6. Sign in as Priya → should now see the event in /events
--
-- ✅ US8.6 - Coordinators Only See Assigned Events:
--    1. Sign in as coordinator@spmg3t7.edu (Priya)
--    2. Should see "Workshop Series - Assigned to Priya"
--    3. Should NOT see "Training Seminar - Assigned to Sam"
--    4. Sign in as coordinator2@spmg3t7.edu (Sam)
--    5. Should see "Training Seminar - Assigned to Sam"
--    6. Should NOT see "Workshop Series - Assigned to Priya"
--    7. Sign in as Coordinator Lead
--    8. Should see BOTH events in /events
--
-- =============================================================================
