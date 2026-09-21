-- US9.1a: venue records carry their supported layouts.
-- Apply once to an existing Supabase project before deploying the venue write
-- endpoints. Safe to run repeatedly: IF NOT EXISTS makes a second run a no-op.
--
-- Required by POST /venues and PUT /venues/{id}. Without this column those two
-- routes fail against the database, because they send `supported_layouts` on
-- every write. GET /venues also selects it, so the read routes need it too.
--
-- Nullable on purpose. US9.1a lists supported layouts as optional, and every
-- row that predates this column has none — inventing a value would be worse
-- than leaving it absent.
ALTER TABLE public.venues
ADD COLUMN IF NOT EXISTS supported_layouts TEXT;

-- Verify the column is there and the venues table still reads as expected.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venues'
ORDER BY ordinal_position;
