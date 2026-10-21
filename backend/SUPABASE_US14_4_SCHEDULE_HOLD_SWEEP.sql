-- US14.4, step 2 of 2: run the hold sweep every 15 minutes with pg_cron.
--
-- RUN THIS ONLY AFTER the US14.4 code is merged into main and everyone on the
-- team has pulled it. From the first run, holds past their expiry are written
-- as Expired, and code from before US14.4 cannot read that status: every
-- bookings, holds and venue page on an older checkout would answer 500.
--
-- Apply after SUPABASE_US14_4_HOLD_EXPIRY.sql (step 1). Safe to run
-- repeatedly: scheduling a job name that already exists replaces it.
--
-- pg_cron runs inside the database, so the sweep happens whether or not anyone
-- has the backend running. If CREATE EXTENSION is refused, enable pg_cron from
-- the dashboard instead (Integrations -> Cron, or Database -> Extensions ->
-- pg_cron) and run the rest of this script.

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;

-- "At least every 15 minutes" (team-chosen): at :00, :15, :30 and :45.
-- tests/test_hold_expiry_us14_4.py reads this line to check the interval.
SELECT cron.schedule(
    'sweep-tentative-holds',
    '*/15 * * * *',
    'SELECT public.sweep_tentative_holds()'
);

-- Verify the job is there and active.
SELECT jobid, jobname, schedule, command, active
FROM cron.job WHERE jobname = 'sweep-tentative-holds';

-- Useful afterwards (not run by this script):
--
--   Run it now, without waiting:
--     SELECT public.sweep_tentative_holds();
--
--   Its last ten runs, and whether they succeeded:
--     SELECT start_time, status, return_message
--     FROM cron.job_run_details
--     WHERE jobid = (SELECT jobid FROM cron.job WHERE jobname = 'sweep-tentative-holds')
--     ORDER BY start_time DESC LIMIT 10;
--
--   Stop it:
--     SELECT cron.unschedule('sweep-tentative-holds');
