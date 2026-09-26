insert into public.venues (name, location, capacity, facilities, accessibility_features, operating_hours, supported_layouts)
values
  ('Marina Grand Ballroom', 'Marina Bay, Singapore', 500, array['stage', 'AV system', 'catering area'], array['wheelchair access', 'accessible toilets', 'lift'], '07:00-23:00', array['banquet', 'exhibition']),
  ('Orchard Conference Hall', 'Orchard Road, Singapore', 300, array['projector', 'stage', 'AV system'], array['wheelchair access', 'hearing loop'], '08:00-22:00', array['theatre', 'banquet']),
  ('Riverside Function Room A', 'Clarke Quay, Singapore', 40, array['whiteboard', 'projector'], array['wheelchair access', 'lift'], '08:00-20:00', array['classroom', 'boardroom']),
  ('Riverside Function Room B', 'Clarke Quay, Singapore', 40, array['whiteboard'], array['wheelchair access', 'lift'], '08:00-20:00', array['classroom', 'boardroom']),
  ('Harbourfront Seminar Room', 'HarbourFront, Singapore', 25, array['whiteboard', 'projector'], array[]::text[], '08:00-18:00', array['classroom']),
  ('Raffles Place Meeting Pod', 'Raffles Place, Singapore', 8, array['screen', 'video conferencing'], array['wheelchair access'], '09:00-21:00', array['boardroom']),
  ('Sentosa Terrace Garden', 'Sentosa, Singapore', 150, array['outdoor seating', 'power outlets'], array[]::text[], '10:00-20:00', array['reception', 'exhibition']),
  ('Bugis Lecture Theatre', 'Bugis, Singapore', 200, array['projector', 'recording equipment'], array['wheelchair access', 'hearing loop', 'reserved seating'], '08:00-21:00', array['theatre']),
  ('Tanjong Pagar Rooftop Lounge', 'Tanjong Pagar, Singapore', 100, array['bar counter', 'outdoor seating', 'AV system'], array[]::text[], '11:00-23:00', array['reception', 'cocktail']),
  ('Jurong Innovation Hub', 'Jurong East, Singapore', 60, array['whiteboard', 'projector', 'breakout pods'], array['wheelchair access', 'accessible toilets'], '08:00-19:00', array['classroom', 'workshop']),
  ('Kallang Sports Hall', 'Kallang, Singapore', 800, array['stage', 'sound system', 'seating tiers'], array['wheelchair access', 'accessible toilets', 'lift', 'reserved seating'], '06:00-23:00', array['exhibition', 'concert']),
  ('Tiong Bahru Studio', 'Tiong Bahru, Singapore', 20, array['natural lighting', 'screen'], array[]::text[], '09:00-18:00', array['workshop', 'boardroom']),
  ('Changi Business Park Auditorium', 'Changi Business Park, Singapore', 350, array['stage', 'AV system', 'interpretation booth'], array['wheelchair access', 'hearing loop', 'lift'], '07:00-22:00', array['theatre', 'banquet']),
  ('Holland Village Garden Room', 'Holland Village, Singapore', 70, array['outdoor seating', 'catering area'], array[]::text[], '10:00-21:00', array['reception', 'garden party']),
  ('Novena Conference Suite', 'Novena, Singapore', 45, array['projector', 'video conferencing', 'whiteboard'], array['wheelchair access', 'accessible toilets'], '08:00-19:00', array['boardroom', 'classroom']),
  ('Punggol Waterway Pavilion', 'Punggol, Singapore', 120, array['outdoor seating', 'power outlets', 'AV system'], array['wheelchair access', 'step-free entry'], '10:00-22:00', array['reception', 'exhibition']);
