"""Safety checks for the cleanup selector; no live database calls."""
import importlib.util
import unittest
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('cleanup_data', Path(__file__).with_name('cleanup-data.py'))
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)
PREFIX = 'Ariel-E2E-1793425347768-r6wwki'


class CleanupSafetyTests(unittest.TestCase):
    def response(self, api, **kwargs):
        challenge = kwargs['params']['challenge']
        return cleanup.httpx.Response(200, request=cleanup.httpx.Request('GET', api),
            json={'proof': cleanup.proof('https://project-a.supabase.co', 'fake-service-key', challenge)})

    def test_matching_database_proof_passes_with_fresh_challenges(self):
        challenges = []

        def fetch(api, **kwargs):
            challenges.append(kwargs['params']['challenge'])
            return self.response(api, **kwargs)

        with patch.object(cleanup.config, 'supabase_url', return_value='https://project-a.supabase.co/'), \
             patch.object(cleanup.config, 'supabase_service_role_key', return_value='fake-service-key'):
            cleanup.verify_api_identity('http://backend-a', fetch)
            cleanup.verify_api_identity('http://backend-a', fetch)
        self.assertNotEqual(challenges[0], challenges[1])

    def test_different_api_project_refuses_before_inventory_or_deletion(self):
        with patch.object(cleanup.config, 'supabase_url', return_value='https://project-b.supabase.co'), \
             patch.object(cleanup.config, 'supabase_service_role_key', return_value='fake-service-key'), \
             patch.object(cleanup.httpx, 'get', side_effect=self.response), \
             patch.object(cleanup.supabase_client, 'admin') as admin, \
             patch.object(cleanup, 'snapshot') as snapshot, \
             patch.object(cleanup.sys, 'argv', ['cleanup-data.py', '--prefix', PREFIX, '--apply', '--verify-api', 'http://backend-a']):
            with self.assertRaisesRegex(RuntimeError, 'identity could not be verified'):
                cleanup.main()
            admin.assert_not_called()
            snapshot.assert_not_called()

    def test_missing_identity_endpoint_is_refused(self):
        response = cleanup.httpx.Response(404, request=cleanup.httpx.Request('GET', 'http://backend'))
        with self.assertRaisesRegex(RuntimeError, 'identity could not be verified'):
            cleanup.verify_api_identity('http://backend', lambda *args, **kwargs: response)

    def test_same_project_with_different_credentials_is_refused(self):
        with patch.object(cleanup.config, 'supabase_url', return_value='https://project-a.supabase.co'), \
             patch.object(cleanup.config, 'supabase_service_role_key', return_value='different-key'), \
             self.assertRaisesRegex(RuntimeError, 'identity could not be verified'):
            cleanup.verify_api_identity('http://backend', self.response)

    def test_manual_deletion_without_api_verification_is_refused(self):
        with patch.object(cleanup.sys, 'argv', ['cleanup-data.py', '--prefix', PREFIX, '--apply']), \
             patch.object(cleanup.supabase_client, 'admin') as admin, \
             patch('sys.stderr'), self.assertRaises(SystemExit):
            cleanup.main()
        admin.assert_not_called()

    def test_replayed_proof_is_refused(self):
        response = cleanup.httpx.Response(200, request=cleanup.httpx.Request('GET', 'http://backend'),
            json={'proof': cleanup.proof('https://project-a.supabase.co', 'fake-service-key', 'old-challenge')})
        with patch.object(cleanup.config, 'supabase_url', return_value='https://project-a.supabase.co'), \
             patch.object(cleanup.config, 'supabase_service_role_key', return_value='fake-service-key'), \
             self.assertRaisesRegex(RuntimeError, 'identity could not be verified'):
            cleanup.verify_api_identity('http://backend', lambda *args, **kwargs: response)

    def test_identity_timeout_is_refused(self):
        with patch.object(cleanup.httpx, 'get', side_effect=cleanup.httpx.ConnectTimeout('offline')), \
             self.assertRaisesRegex(RuntimeError, 'identity could not be verified'):
            cleanup.verify_api_identity('http://backend')

    def data(self):
        data = {t: [] for t in cleanup.TABLES}
        data['events'] = [{'id': 1, 'name': PREFIX + ' event', 'purpose': 'Playwright regression'},
                          {'id': 2, 'name': 'Real event', 'purpose': 'Real work'}]
        data['venues'] = [{'id': 3, 'name': PREFIX + ' venue 0', 'location': 'E2E store'}]
        data['venue_bookings'] = [{'id': 4, 'event_id': 1, 'venue_id': 3}]
        return data

    def test_only_owned_events_and_dependents_selected(self):
        owned = cleanup.select_owned(self.data(), PREFIX)
        self.assertEqual(owned['events'], {1})
        self.assertEqual(owned['venue_bookings'], {4})

    def test_real_event_using_test_venue_blocks_deletion(self):
        data = self.data()
        data['venue_bookings'].append({'id': 5, 'event_id': 2, 'venue_id': 3})
        with self.assertRaisesRegex(ValueError, 'Non-test reference'):
            cleanup.select_owned(data, PREFIX)

    def test_another_runs_records_are_not_selected(self):
        self.assertFalse(any(cleanup.select_owned(self.data(), 'Ariel-E2E-1793425347769-abcdef').values()))

    def test_unexpected_metadata_blocks_deletion(self):
        data = self.data()
        data['venues'][0]['location'] = 'Real store'
        with self.assertRaisesRegex(ValueError, 'Unexpected location'):
            cleanup.select_owned(data, PREFIX)

    def test_unavailability_added_by_someone_else_blocks_deletion(self):
        data = self.data()
        data['venue_unavailability'] = [{'id': 8, 'venue_id': 3}]
        with self.assertRaisesRegex(ValueError, 'Non-test reference'):
            cleanup.select_owned(data, PREFIX)

    def test_broad_unrelated_prefix_is_refused(self):
        with self.assertRaises(ValueError):
            cleanup.select_owned(self.data(), 'Ariel')

    def test_transient_connection_failure_recovers(self):
        calls = []

        def operation():
            calls.append(1)
            if len(calls) == 1:
                raise cleanup.httpx.ConnectError('temporary disconnect')
            return 'ok'

        with patch.object(cleanup.time, 'sleep'):
            self.assertEqual(cleanup.transport_retry(operation), 'ok')
        self.assertEqual(len(calls), 2)

    def test_permanent_connection_failure_is_not_hidden(self):
        calls = []

        def operation():
            calls.append(1)
            raise cleanup.httpx.ConnectError('offline')

        with patch.object(cleanup.time, 'sleep'), self.assertRaises(cleanup.httpx.ConnectError):
            cleanup.transport_retry(operation)
        self.assertEqual(len(calls), 3)


if __name__ == '__main__':
    unittest.main()
