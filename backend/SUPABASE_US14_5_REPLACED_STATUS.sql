-- US14.5: Add 'Replaced' status to booking_status enum for replacement bookings
-- A booking marked 'Replaced' is kept for history but no longer holds its venue.

-- Add the new status value
ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'Replaced';

-- Document that 'Replaced' is a terminal status like 'Cancelled' and 'Rejected'
-- and that replaced bookings are kept in the database for audit trail purposes.
