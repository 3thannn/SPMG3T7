/**
 * US12.2: Add partial index for 'Needs replacement' booking status
 *
 * This must be run AFTER the main US12.2 migration has been committed,
 * because PostgreSQL requires enum values to be committed before they
 * can be used in index predicates.
 */

-- Add partial index for efficient queries on 'Needs replacement' bookings
CREATE INDEX IF NOT EXISTS ix_venue_bookings_needs_replacement
    ON public.venue_bookings (status)
    WHERE status = 'Needs replacement';
