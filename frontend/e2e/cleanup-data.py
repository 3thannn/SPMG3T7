"""Back up and remove only Ariel E2E records. Run with backend's Python environment."""
import argparse
import hmac
import json
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import load_dotenv

load_dotenv(ROOT / 'backend' / '.env')
from app import supabase_client
from app import config
import httpx
from database_identity import proof

TABLES = ['safety_review_flags', 'registrations', 'notifications',
          'equipment_request_history', 'event_changes', 'event_change_requests',
          'status_changes', 'safety_reviews', 'equipment_requests', 'venue_bookings',
          'venue_unavailability', 'events', 'equipment', 'venues']
REFERENCES = {'event_id': 'events', 'venue_id': 'venues', 'equipment_id': 'equipment',
              'requested_equipment_id': 'equipment', 'equipment_request_id': 'equipment_requests',
              'request_id': 'equipment_requests', 'booking_id': 'venue_bookings',
              'decision_id': 'safety_reviews'}


def transport_retry(operation):
    # Only used for reads and exact-ID cleanup deletes (both idempotent), never
    # application writes/RPCs that might already have committed.
    for attempt in range(3):
        try:
            return operation()
        except httpx.TransportError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def verify_api_identity(api_url, fetch=None):
    fetch = fetch or httpx.get
    challenge = secrets.token_hex(32)
    expected = proof(config.supabase_url(), config.supabase_service_role_key(), challenge)
    try:
        response = fetch(api_url.rstrip('/') + '/__e2e__/database-identity',
                         params={'challenge': challenge}, timeout=15, follow_redirects=False)
        response.raise_for_status()
        received = response.json().get('proof')
        if not isinstance(received, str) or not hmac.compare_digest(expected, received):
            raise ValueError('Database identity mismatch')
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        # Do not echo response bodies, credentials, or connection details.
        raise RuntimeError('API database identity could not be verified. Start the E2E backend wrapper '
                           'with the same Supabase configuration as cleanup; no cleanup was performed.') from None


def snapshot(client):
    result = {}
    for table in TABLES:
        rows = []
        start = 0
        while True:
            page = transport_retry(lambda: client.table(table).select('*').order('id').range(start, start + 499).execute()).data
            rows.extend(page)
            if len(page) < 500:
                break
            start += 500
        result[table] = rows
    return result


def select_owned(data, prefix):
    if prefix != 'Ariel-E2E-' and not re.fullmatch(r'Ariel-E2E-\d{13}-[a-z0-9]{6}', prefix):
        raise ValueError('Expected an exact run prefix, or Ariel-E2E- for legacy recovery')
    owned = {t: set() for t in TABLES}
    for table in ['events', 'venues', 'equipment']:
        for row in data[table]:
            name = row['name']
            if name.startswith(prefix) and re.match(r'^Ariel-E2E-\d{13}-[a-z0-9]{6} ', name):
                if table != 'events' and row.get('location') != 'E2E store':
                    raise ValueError(f'Unexpected location for {table}/{row["id"]}')
                if table == 'events' and row.get('purpose') not in ['Playwright regression', 'Updated draft purpose']:
                    raise ValueError(f'Unexpected purpose for events/{row["id"]}')
                owned[table].add(row['id'])
    for table in TABLES:
        if table in ['events', 'venues', 'equipment']:
            continue
        for row in data[table]:
            if row.get('event_id') in owned['events']:
                owned[table].add(row['id'])
    # Refuse to remove a resource now referenced by someone else's work.
    for table, rows in data.items():
        for row in rows:
            if row['id'] not in owned[table]:
                for column, target in REFERENCES.items():
                    if row.get(column) in owned[target]:
                        raise ValueError(f'Non-test reference: {table}/{row["id"]} -> {target}')
    return owned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--check', action='store_true', help='Fail if any owned rows remain')
    parser.add_argument('--baseline', type=Path, help='Verify non-test rows against a cleanup backup')
    parser.add_argument('--verify-api', help='Require a fresh API database proof before inventory or deletion')
    args = parser.parse_args()
    if args.apply and not args.verify_api:
        parser.error('--apply requires --verify-api pointing to the backend under test')
    if args.verify_api:
        verify_api_identity(args.verify_api)
    client = supabase_client.admin()
    before = snapshot(client)
    owned = select_owned(before, args.prefix)
    # Other active E2E runs may legitimately change their own rows while this
    # cleanup runs. Preservation checks concern original application data.
    all_test = select_owned(before, 'Ariel-E2E-')
    counts = {t: len(ids) for t, ids in owned.items() if ids}
    print(json.dumps({'prefix': args.prefix, 'records': counts}))
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
        for table, rows in baseline['before'].items():
            now = {r['id']: r for r in before[table]}
            removed = set(baseline['ids'][table])
            for row in rows:
                if row['id'] not in removed and now.get(row['id']) != row:
                    raise RuntimeError(f'Non-test row differs from baseline: {table}/{row["id"]}')
        print('Baseline verified: every original non-test row is unchanged.')
    if args.check and counts:
        raise RuntimeError('Test records remain')
    if not args.apply or not counts:
        return
    folder = ROOT / 'frontend' / 'playwright' / '.cache' / 'cleanup'
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    backup.write_text(json.dumps({'prefix': args.prefix, 'ids': {t: sorted(v) for t, v in owned.items()},
                                 'before': before}, indent=2), encoding='utf-8')
    print(f'Backup: {backup}')
    # Exact IDs only, with the identity rechecked immediately before mutation.
    # Child rows go first; FK restrictions remain enabled throughout.
    current = snapshot(client)
    if select_owned(current, args.prefix) != owned:
        raise RuntimeError('Test inventory changed; rerun inventory before cleanup')
    for table in TABLES:
        ids = sorted(owned[table])
        if ids:
            transport_retry(lambda: client.table(table).delete().in_('id', ids).execute())
    after = snapshot(client)
    if any(select_owned(after, args.prefix).values()):
        raise RuntimeError('Cleanup incomplete; recovery backup saved')
    for table, rows in before.items():
        untouched = {r['id']: r for r in rows if r['id'] not in all_test[table]}
        now = {r['id']: r for r in after[table]}
        for key, value in untouched.items():
            if now.get(key) != value:
                raise RuntimeError(f'Non-test row changed during cleanup: {table}/{key}; inspect backup')
    print('Cleanup verified: no test rows remain; all pre-existing non-test rows are unchanged.')


if __name__ == '__main__':
    main()
