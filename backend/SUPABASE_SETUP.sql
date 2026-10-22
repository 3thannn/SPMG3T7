-- SPMG3T7 Database Schema - Manual Setup for Supabase
-- Run this in Supabase SQL Editor if migrations don't work
-- Go to: Supabase Dashboard → SQL Editor → New Query → Paste this

-- Create custom types for enums
CREATE TYPE user_role AS ENUM (
    'Event Organiser',
    'Event Coordinator',
    'Venue Staff',
    'Technical Support',
    'Attendee'
);

CREATE TYPE event_status AS ENUM (
    'Draft',
    'Submitted',
    'Under Review',
    'Approved',
    'Planning',
    -- US4.4: see SUPABASE_ADD_SAFETY_CHECK_STATUS.sql for its transitions.
    'Pending Safety Check',
    'Confirmed',
    'Completed',
    'Cancelled',
    'Rejected'
);

-- US14.1 and US14.2: a new booking is Requested and a Coordinator may cancel
-- it. US14.3: Venue Staff may place a tentative Held booking. The Venue
-- Booking Approval epic adds the statuses Venue Staff set.
CREATE TYPE booking_status AS ENUM (
    'Requested',
    'Cancelled',
    'Held',
    -- US16.1: Venue Staff decide a request.
    'Confirmed',
    'Rejected'
);

-- Create users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    role user_role NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_users_email ON users(email);
CREATE INDEX ix_users_id ON users(id);

-- Create venues table
CREATE TABLE venues (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    location VARCHAR(500) NOT NULL,
    capacity INTEGER NOT NULL,
    facilities TEXT,
    accessibility_features TEXT,
    operating_hours VARCHAR(255),
    -- US9.1a names supported layouts as an optional field on a venue record.
    supported_layouts TEXT,
    -- US9.4: see SUPABASE_ADD_VENUE_TURNAROUND.sql.
    setup_minutes INTEGER NOT NULL DEFAULT 0
        CONSTRAINT venues_setup_minutes_range CHECK (setup_minutes BETWEEN 0 AND 1440),
    turnaround_minutes INTEGER NOT NULL DEFAULT 0
        CONSTRAINT venues_turnaround_minutes_range CHECK (turnaround_minutes BETWEEN 0 AND 1440),
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_venues_name ON venues(name);
CREATE INDEX ix_venues_id ON venues(id);

-- Create equipment table
CREATE TABLE equipment (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    equipment_type VARCHAR(100) NOT NULL,
    quantity_available INTEGER NOT NULL DEFAULT 0,
    technical_specs TEXT,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_equipment_equipment_type ON equipment(equipment_type);
CREATE INDEX ix_equipment_id ON equipment(id);

-- Create events table
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    purpose VARCHAR(500),
    description TEXT,
    proposed_date TIMESTAMP,
    end_date TIMESTAMP,
    expected_attendance INTEGER,
    -- US2.1 (Sprint 3): see SUPABASE_ADD_EVENT_NEEDS.sql.
    venue_requirements TEXT,
    preferred_layout TEXT,
    accessibility_needs TEXT,
    equipment_needs TEXT,
    registration_needs TEXT,
    status event_status NOT NULL DEFAULT 'Draft',
    organiser_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    submitted_at TIMESTAMP
);

CREATE INDEX ix_events_id ON events(id);
CREATE INDEX ix_events_organiser_id ON events(organiser_id);
CREATE INDEX ix_events_status ON events(status);

-- Create status_changes table
CREATE TABLE status_changes (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id),
    old_status event_status NOT NULL,
    new_status event_status NOT NULL,
    changed_by_id INTEGER NOT NULL REFERENCES users(id),
    changed_at TIMESTAMP DEFAULT NOW() NOT NULL,
    notes TEXT
);

CREATE INDEX ix_status_changes_id ON status_changes(id);
CREATE INDEX ix_status_changes_event_id ON status_changes(event_id);
CREATE INDEX ix_status_changes_changed_by_id ON status_changes(changed_by_id);

-- US12.1: date ranges a venue cannot be used. Inclusive at both ends; see
-- SUPABASE_ADD_VENUE_UNAVAILABILITY.sql for why each constraint is what it is.
CREATE TABLE venue_unavailability (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT,
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    CONSTRAINT venue_unavailability_end_not_before_start CHECK (end_date >= start_date)
);

CREATE INDEX ix_venue_unavailability_venue_start
    ON venue_unavailability(venue_id, start_date);
CREATE INDEX ix_venue_unavailability_created_by_id
    ON venue_unavailability(created_by_id);

-- US10.1: an Organiser's in-app notices about their events' status changes.
-- See SUPABASE_ADD_NOTIFICATIONS.sql for why each column is what it is.
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    status event_status NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    read_at TIMESTAMP
);

CREATE INDEX ix_notifications_user_read_created
    ON notifications(user_id, is_read, created_at DESC);
CREATE INDEX ix_notifications_event_id ON notifications(event_id);
-- US14.1: one row per venue an event asks for; US14.2 adds cancelling one and
-- US18.1 what it needs. See SUPABASE_ADD_VENUE_BOOKINGS.sql,
-- SUPABASE_CANCEL_VENUE_BOOKINGS.sql and SUPABASE_ADD_BOOKING_NEEDS.sql for why
-- each constraint is what it is.
CREATE TABLE venue_bookings (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    venue_id INTEGER NOT NULL REFERENCES venues(id),
    start_at TIMESTAMP NOT NULL,
    end_at TIMESTAMP NOT NULL,
    status booking_status NOT NULL DEFAULT 'Requested',
    requested_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    -- US18.1: what the booking needs of a venue. See SUPABASE_ADD_BOOKING_NEEDS.sql.
    headcount INTEGER,
    required_layout TEXT,
    required_facilities TEXT[] NOT NULL DEFAULT '{}',
    accessibility_needs TEXT[] NOT NULL DEFAULT '{}',
    cancelled_at TIMESTAMP,
    cancellation_reason TEXT,
    cancelled_by_id INTEGER,
    -- US14.3: a hold's expiry and who placed it. See SUPABASE_ADD_VENUE_HOLDS.sql.
    hold_expires_at TIMESTAMP,
    held_by_id INTEGER,
    -- US16.1: the decision. See SUPABASE_ADD_BOOKING_DECISIONS.sql.
    decided_at TIMESTAMP,
    decided_by_id INTEGER,
    rejection_reason TEXT,
    suggested_alternative TEXT,
    -- US15.2: flagged "Conflict - review needed". See SUPABASE_ADD_BOOKING_CONFLICTS.sql.
    conflict_flagged_at TIMESTAMP,
    conflict_reason TEXT,
    CONSTRAINT venue_bookings_end_after_start CHECK (end_at > start_at),
    CONSTRAINT venue_bookings_headcount_positive CHECK (headcount IS NULL OR headcount >= 1),
    CONSTRAINT venue_bookings_cancelled_by_id_fkey
        FOREIGN KEY (cancelled_by_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT venue_bookings_held_by_id_fkey
        FOREIGN KEY (held_by_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT venue_bookings_hold_has_expiry CHECK (
        status <> 'Held' OR hold_expires_at IS NOT NULL
    ),
    CONSTRAINT venue_bookings_decided_by_id_fkey
        FOREIGN KEY (decided_by_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT venue_bookings_decision_recorded CHECK (
        (status IN ('Confirmed', 'Rejected')) = (decided_at IS NOT NULL)
    ),
    CONSTRAINT venue_bookings_rejection_has_reason CHECK (
        status <> 'Rejected'
        OR (rejection_reason IS NOT NULL AND btrim(rejection_reason) <> '')
    ),
    CONSTRAINT venue_bookings_cancellation_recorded CHECK (
        (status = 'Cancelled') = (
            cancelled_at IS NOT NULL
            AND cancellation_reason IS NOT NULL
            AND btrim(cancellation_reason) <> ''
        )
    ),
    CONSTRAINT venue_bookings_conflict_has_reason CHECK (
        conflict_flagged_at IS NULL
        OR (conflict_reason IS NOT NULL AND btrim(conflict_reason) <> '')
    )
);

CREATE INDEX ix_venue_bookings_event_start ON venue_bookings(event_id, start_at);
CREATE INDEX ix_venue_bookings_venue_id ON venue_bookings(venue_id);
CREATE INDEX ix_venue_bookings_requested_by_id ON venue_bookings(requested_by_id);
CREATE INDEX ix_venue_bookings_cancelled_by_id ON venue_bookings(cancelled_by_id);
CREATE INDEX ix_venue_bookings_held_by_id ON venue_bookings(held_by_id);
CREATE INDEX ix_venue_bookings_decided_by_id ON venue_bookings(decided_by_id);
CREATE INDEX ix_venue_bookings_status_created ON venue_bookings(status, created_at);
CREATE INDEX ix_venue_bookings_conflict_flagged
    ON venue_bookings(start_at) WHERE conflict_flagged_at IS NOT NULL;

-- US7.1: keep a Coordinator decision and its US4.2 audit row in one transaction.
-- Transition validation remains in Python; this is not a status trigger.
CREATE OR REPLACE FUNCTION public.decide_event_status(
    p_event_id INTEGER,
    p_expected_status public.event_status,
    p_new_status public.event_status,
    p_changed_by_id INTEGER,
    p_notes TEXT DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    decision_at TIMESTAMP := NOW();
BEGIN
    UPDATE public.events
    SET status = p_new_status,
        updated_at = decision_at
    WHERE id = p_event_id
      AND status = p_expected_status;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    INSERT INTO public.status_changes (
        event_id,
        old_status,
        new_status,
        changed_by_id,
        changed_at,
        notes
    )
    VALUES (
        p_event_id,
        p_expected_status,
        p_new_status,
        p_changed_by_id,
        decision_at,
        p_notes
    );

    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.decide_event_status(
    INTEGER,
    public.event_status,
    public.event_status,
    INTEGER,
    TEXT
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.decide_event_status(
    INTEGER,
    public.event_status,
    public.event_status,
    INTEGER,
    TEXT
) TO service_role;

-- Create trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = '';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_events_updated_at BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_venues_updated_at BEFORE UPDATE ON venues
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_equipment_updated_at BEFORE UPDATE ON equipment
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- The browser calls the FastAPI backend, never the Supabase Data API directly.
-- Keep these public-schema tables unavailable to anon/authenticated API clients;
-- the backend's service-role client retains the access it needs.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE status_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE venues ENABLE ROW LEVEL SECURITY;
ALTER TABLE equipment ENABLE ROW LEVEL SECURITY;
ALTER TABLE venue_unavailability ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE venue_bookings ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE users, events, status_changes, venues, equipment,
    venue_unavailability, notifications, venue_bookings FROM anon, authenticated;

-- Verify tables were created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
