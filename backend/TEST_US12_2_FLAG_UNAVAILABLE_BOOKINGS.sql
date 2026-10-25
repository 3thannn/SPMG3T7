/**
 * US12.2 Test Cases: Flag bookings hit by venue unavailability
 *
 * These tests verify that the database trigger correctly flags active bookings
 * when a venue is marked unavailable, and that Coordinators are notified once per event.
 */

-- Setup: Clear existing test data
DELETE FROM public.notifications WHERE event_id IN (SELECT id FROM public.events WHERE title LIKE 'US12.2 Test%');
DELETE FROM public.bookings WHERE event_id IN (SELECT id FROM public.events WHERE title LIKE 'US12.2 Test%');
DELETE FROM public.events WHERE title LIKE 'US12.2 Test%';
DELETE FROM public.venue_unavailability WHERE venue_id IN (SELECT id FROM public.venues WHERE name LIKE 'US12.2 Test%');
DELETE FROM public.venues WHERE name LIKE 'US12.2 Test%';
DELETE FROM public.users WHERE name LIKE 'US12.2 Test%';

-- Create test users
INSERT INTO public.users (id, name, email, role, password_hash)
VALUES
    (9001, 'US12.2 Test Coordinator', 'coord12.2@test.com', 'Event Coordinator', 'hash'),
    (9002, 'US12.2 Test Venue Staff', 'venue12.2@test.com', 'Venue Staff', 'hash')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

-- Create test venue
INSERT INTO public.venues (id, name, location, capacity, setup_minutes, turnaround_minutes)
VALUES (9001, 'US12.2 Test Hall', 'Test Building', 100, 30, 30)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

-- Create test events
INSERT INTO public.events (id, title, purpose, description, starts_at, ends_at, expected_attendance, status, organiser_id, coordinator_id)
VALUES
    (9001, 'US12.2 Test Event 1 - Confirmed booking', 'Test', 'Event with confirmed booking on 11 Nov', '2027-11-11 14:00:00+08', '2027-11-11 16:00:00+08', 50, 'Approved', 9001, 9001),
    (9002, 'US12.2 Test Event 2 - Cancelled booking', 'Test', 'Event with cancelled booking on 11 Nov', '2027-11-11 14:00:00+08', '2027-11-11 16:00:00+08', 50, 'Approved', 9001, 9001),
    (9003, 'US12.2 Test Event 3 - Outside range', 'Test', 'Event with booking on 20 Nov (outside unavailability)', '2027-11-20 14:00:00+08', '2027-11-20 16:00:00+08', 50, 'Approved', 9001, 9001),
    (9004, 'US12.2 Test Event 4 - Two bookings', 'Test', 'Event with two bookings at same venue', '2027-11-11 10:00:00+08', '2027-11-11 12:00:00+08', 50, 'Approved', 9001, 9001)
ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title;

-- Create test bookings
INSERT INTO public.bookings (id, event_id, venue_id, starts_at, ends_at, status, requested_by_id, requested_at, headcount)
VALUES
    -- Event 1: Confirmed booking on 11 Nov (should be flagged)
    (9001, 9001, 9001, '2027-11-11 14:00:00+08', '2027-11-11 16:00:00+08', 'Confirmed', 9001, NOW(), 50),

    -- Event 2: Cancelled booking on 11 Nov (should NOT be flagged)
    (9002, 9002, 9001, '2027-11-11 14:00:00+08', '2027-11-11 16:00:00+08', 'Cancelled', 9001, NOW(), 50),

    -- Event 3: Confirmed booking on 20 Nov (should NOT be flagged - outside range)
    (9003, 9003, 9001, '2027-11-20 14:00:00+08', '2027-11-20 16:00:00+08', 'Confirmed', 9001, NOW(), 50),

    -- Event 4: Two confirmed bookings on 11 Nov (both should be flagged, but only ONE notification)
    (9004, 9004, 9001, '2027-11-11 10:00:00+08', '2027-11-11 12:00:00+08', 'Confirmed', 9001, NOW(), 25),
    (9005, 9004, 9001, '2027-11-11 15:00:00+08', '2027-11-11 17:00:00+08', 'Confirmed', 9001, NOW(), 25)
ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;

-- TEST CASE 1: Mark venue unavailable 10-12 Nov with maintenance reason
-- Expected: Bookings 9001, 9004, 9005 flagged; Booking 9002 (Cancelled) and 9003 (outside range) NOT flagged
-- Expected: 2 notifications created (one for Event 1, one for Event 4)

SELECT '=== TEST CASE 1: Before marking venue unavailable ===' AS test_step;

SELECT
    b.id AS booking_id,
    e.title AS event_title,
    b.status,
    b.replacement_reason,
    b.flagged_by_unavailability_id
FROM public.bookings b
JOIN public.events e ON b.event_id = e.id
WHERE b.id IN (9001, 9002, 9003, 9004, 9005)
ORDER BY b.id;

-- Count notifications before
SELECT COUNT(*) AS notifications_before
FROM public.notifications
WHERE user_id = 9001 AND kind = 'booking-conflict';

-- Now mark the venue unavailable
INSERT INTO public.venue_unavailability (venue_id, start_date, end_date, reason_type, created_by_id)
VALUES (9001, '2027-11-10', '2027-11-12', 'maintenance', 9002)
RETURNING id, venue_id, start_date, end_date, reason_type, other_reason;

SELECT '=== TEST CASE 1: After marking venue unavailable ===' AS test_step;

-- Check bookings after flagging
SELECT
    b.id AS booking_id,
    e.title AS event_title,
    b.status,
    b.replacement_reason,
    b.flagged_by_unavailability_id
FROM public.bookings b
JOIN public.events e ON b.event_id = e.id
WHERE b.id IN (9001, 9002, 9003, 9004, 9005)
ORDER BY b.id;

-- Verify notifications
SELECT
    n.id,
    n.user_id,
    e.title AS event_title,
    n.kind,
    n.message,
    n.is_read
FROM public.notifications n
JOIN public.events e ON n.event_id = e.id
WHERE n.user_id = 9001 AND n.kind = 'booking-conflict'
ORDER BY n.created_at DESC
LIMIT 10;

-- EXPECTED RESULTS:
-- Booking 9001: status = 'Needs replacement', replacement_reason = 'scheduled maintenance'
-- Booking 9002: status = 'Cancelled' (unchanged)
-- Booking 9003: status = 'Confirmed' (unchanged - outside range)
-- Booking 9004: status = 'Needs replacement', replacement_reason = 'scheduled maintenance'
-- Booking 9005: status = 'Needs replacement', replacement_reason = 'scheduled maintenance'
-- Notifications: 2 new notifications (one for event 9001, one for event 9004)

SELECT '=== TEST CASE 1: Verification ===' AS test_step;

-- Count flagged bookings
SELECT COUNT(*) AS flagged_bookings_count
FROM public.bookings
WHERE id IN (9001, 9002, 9003, 9004, 9005)
  AND status = 'Needs replacement';
-- Expected: 3

-- Count notifications
SELECT COUNT(*) AS new_notifications_count
FROM public.notifications
WHERE user_id = 9001
  AND kind = 'booking-conflict'
  AND event_id IN (9001, 9004)
  AND created_at > NOW() - INTERVAL '10 seconds';
-- Expected: 2

-- TEST CASE 2: Test 'other' reason type with custom text
DELETE FROM public.venue_unavailability WHERE venue_id = 9001;

-- Reset booking statuses
UPDATE public.bookings
SET status = 'Confirmed', replacement_reason = NULL, flagged_by_unavailability_id = NULL
WHERE id IN (9001, 9004, 9005);

-- Clear notifications
DELETE FROM public.notifications WHERE user_id = 9001 AND kind = 'booking-conflict';

SELECT '=== TEST CASE 2: Custom "other" reason ===' AS test_step;

-- Mark unavailable with custom reason
INSERT INTO public.venue_unavailability (venue_id, start_date, end_date, reason_type, other_reason, created_by_id)
VALUES (9001, '2027-11-10', '2027-11-12', 'other', 'Unexpected flooding in venue', 9002)
RETURNING id, reason_type, other_reason;

-- Check that bookings were flagged with the custom reason
SELECT
    b.id AS booking_id,
    b.status,
    b.replacement_reason
FROM public.bookings b
WHERE b.id IN (9001, 9004, 9005)
ORDER BY b.id;

-- Check notification message includes custom reason
SELECT
    n.message
FROM public.notifications n
WHERE n.user_id = 9001
  AND n.kind = 'booking-conflict'
  AND n.event_id = 9001
ORDER BY n.created_at DESC
LIMIT 1;

-- EXPECTED:
-- replacement_reason should be 'Unexpected flooding in venue'
-- notification message should include 'Unexpected flooding in venue'

-- TEST CASE 3: Test edge case - booking effective window with setup/turnaround
DELETE FROM public.venue_unavailability WHERE venue_id = 9001;
DELETE FROM public.bookings WHERE id = 9010;

-- Reset
UPDATE public.bookings
SET status = 'Confirmed', replacement_reason = NULL, flagged_by_unavailability_id = NULL
WHERE id = 9001;

DELETE FROM public.notifications WHERE user_id = 9001 AND kind = 'booking-conflict';

SELECT '=== TEST CASE 3: Effective window overlap (setup + turnaround) ===' AS test_step;

-- Create a booking that starts at 00:30 on Nov 13 (just after midnight)
-- With 30min setup, effective start is 00:00 on Nov 13
-- Unavailability ends on Nov 12 (which means midnight on Nov 13)
-- So they should just barely NOT overlap
INSERT INTO public.bookings (id, event_id, venue_id, starts_at, ends_at, status, requested_by_id, requested_at, headcount)
VALUES (9010, 9001, 9001, '2027-11-13 00:30:00+08', '2027-11-13 02:00:00+08', 'Confirmed', 9001, NOW(), 50)
ON CONFLICT (id) DO UPDATE SET starts_at = EXCLUDED.starts_at;

-- Mark unavailable ending on Nov 12 (midnight on Nov 13)
INSERT INTO public.venue_unavailability (venue_id, start_date, end_date, reason_type, created_by_id)
VALUES (9001, '2027-11-10', '2027-11-12', 'renovation', 9002);

-- Check if booking 9010 was flagged
SELECT
    b.id AS booking_id,
    b.starts_at,
    b.ends_at,
    b.status,
    b.replacement_reason
FROM public.bookings b
WHERE b.id = 9010;

-- EXPECTED: Booking 9010 should be flagged because:
-- - Booking starts at 2027-11-13 00:30
-- - Venue setup is 30 minutes
-- - Effective start = 2027-11-13 00:00
-- - Unavailability end_date = 2027-11-12 (which is midnight on 2027-11-13 00:00)
-- - Overlap check: effective_start (00:00) < unavail_end + 1 day (2027-11-13 00:00 + 1 day = 2027-11-14 00:00) ✓
-- - AND unavail_start (2027-11-10 00:00) < effective_end (02:30) ✓
-- So YES, it should be flagged

-- Cleanup
SELECT '=== Cleaning up test data ===' AS test_step;

DELETE FROM public.notifications WHERE event_id IN (9001, 9002, 9003, 9004);
DELETE FROM public.bookings WHERE id IN (9001, 9002, 9003, 9004, 9005, 9010);
DELETE FROM public.events WHERE id IN (9001, 9002, 9003, 9004);
DELETE FROM public.venue_unavailability WHERE venue_id = 9001;
DELETE FROM public.venues WHERE id = 9001;
DELETE FROM public.users WHERE id IN (9001, 9002);

SELECT '=== All tests completed ===' AS test_step;
