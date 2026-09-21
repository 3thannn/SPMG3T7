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
    'Confirmed',
    'Completed',
    'Cancelled',
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

REVOKE ALL ON TABLE users, events, status_changes, venues, equipment
FROM anon, authenticated;

-- Verify tables were created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
