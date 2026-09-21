-- US9.2: sample ConnectSphere venues, so the catalogue has something to show.
-- Run once in the Supabase SQL Editor. Safe to run repeatedly: `venues.name` is
-- UNIQUE, so ON CONFLICT leaves an existing row — and any edits made to it —
-- alone rather than overwriting it.
--
-- These are demonstration records, not real ConnectSphere venues. Replace them
-- with the actual catalogue when it arrives; nothing in the code depends on
-- these names or ids.
--
-- Run SUPABASE_ADD_VENUE_LAYOUTS.sql first: this script sets supported_layouts,
-- the column US9.1a added.
--
-- Bertha Room deliberately leaves facilities, accessibility_features,
-- operating_hours and supported_layouts unset. All three columns are nullable, and a half-filled
-- record is the case the catalogue has to render without looking broken — it
-- shows "Not recorded" for each. Keep at least one such row while the story is
-- being reviewed.

INSERT INTO public.venues
    (name, location, capacity, facilities, accessibility_features,
     operating_hours, supported_layouts)
VALUES
    (
        'Great Hall',
        'Main Campus, Building A',
        500,
        'Raised stage, PA system, twin projectors, green room',
        'Step-free access, hearing loop, accessible toilets',
        'Mon-Sat 08:00-22:00',
        'Theatre, standing, cabaret'
    ),
    (
        'Rosewood Auditorium',
        'Main Campus, Building C, Level 2',
        280,
        'Fixed tiered seating, lectern, recording booth',
        'Step-free access, wheelchair spaces in rows A and M',
        'Mon-Fri 09:00-21:00',
        'Fixed tiered seating'
    ),
    (
        'Innovation Studio',
        'Science Quarter, Building F',
        120,
        'Movable staging, 12 breakout tables, dual screens, kitchenette',
        'Step-free access, accessible toilets',
        'Mon-Fri 08:00-20:00',
        'Breakout tables, standing, classroom'
    ),
    (
        'Harbour View Terrace',
        'East Wing rooftop, Building B',
        150,
        'Covered outdoor terrace, bar service point, string lighting',
        'Lift access to rooftop level',
        'Wed-Sun 16:00-23:00',
        'Standing, cabaret'
    ),
    (
        'Seminar Room 4',
        'Library, Level 1',
        60,
        'Boardroom table, wall-mounted screen, video conferencing',
        'Step-free access, hearing loop',
        'Mon-Fri 07:30-19:00',
        'Boardroom, classroom'
    ),
    (
        'Bertha Room',
        'Library, Level 3',
        40,
        NULL,
        NULL,
        NULL,
        NULL
    )
ON CONFLICT (name) DO NOTHING;

-- Verify what the catalogue will list, in the order GET /venues returns it.
SELECT id, name, location, capacity
FROM public.venues
ORDER BY name;
