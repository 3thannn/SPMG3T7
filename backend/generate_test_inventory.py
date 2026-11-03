#!/usr/bin/env python3
"""Generate comprehensive test inventory CSV for all backend and e2e tests."""

import csv
import re
import subprocess
from pathlib import Path
from typing import List, Dict

def classify_test(file_path: str, test_name: str, class_name: str = "") -> str:
    """Classify test as Unit, Integration, or E2E."""
    file_name = Path(file_path).name

    # E2E tests are in frontend
    if 'e2e' in file_path or 'playwright' in file_path:
        return "E2E"

    # Unit tests: store/repository tests
    if any(keyword in file_name for keyword in ['_store.py', '_repository.py']):
        return "Unit"

    # Integration tests: route/API tests (most tests with TestClient)
    if any(keyword in test_name.lower() for keyword in ['route', 'api', 'endpoint']):
        return "Integration"

    # Check class name for hints
    if class_name:
        if any(keyword in class_name for keyword in ['InMemory', 'Supabase', 'Store', 'Repository']):
            return "Unit"
        if any(keyword in class_name for keyword in ['Route', 'API', 'Endpoint']):
            return "Integration"

    # Default heuristic: files with TestClient usage are Integration
    # Files testing business logic/helpers are Unit
    if any(keyword in file_name for keyword in ['test_booking', 'test_venue', 'test_equipment',
                                                  'test_registration', 'test_event', 'test_safety',
                                                  'test_change']):
        return "Integration"  # Most are API tests

    return "Unit"  # Conservative default

def extract_user_story(file_path: str, test_name: str) -> str:
    """Extract user story reference like US9.4, US20.1."""
    file_name = Path(file_path).name

    # Check filename: test_registration_us20_1.py -> US20.1
    match = re.search(r'us(\d+)[_.](\d+)', file_name, re.IGNORECASE)
    if match:
        return f"US{match.group(1)}.{match.group(2)}"

    # Check test name
    match = re.search(r'us[_]?(\d+)[_.](\d+)', test_name, re.IGNORECASE)
    if match:
        return f"US{match.group(1)}.{match.group(2)}"

    return ""

def extract_feature(file_path: str, test_name: str) -> str:
    """Extract feature description from filename."""
    file_name = Path(file_path).stem  # Without .py

    # Map common file patterns to features
    feature_map = {
        'booking': 'Venue Bookings',
        'venue': 'Venue Management',
        'equipment': 'Equipment Requests',
        'registration': 'Event Registration',
        'event': 'Event Management',
        'safety': 'Safety Checks',
        'change_request': 'Change Requests',
        'notification': 'Notifications',
        'suitability': 'Venue Suitability',
        'turnaround': 'Venue Turnaround Times',
        'unavailability': 'Venue Unavailability',
        'conflict': 'Booking Conflicts',
        'hold': 'Venue Holds',
    }

    for keyword, feature in feature_map.items():
        if keyword in file_name.lower():
            return feature

    return file_name.replace('test_', '').replace('_', ' ').title()

def collect_backend_tests() -> List[Dict]:
    """Collect all backend pytest tests with details."""
    tests = []

    # Run pytest with verbose collection
    result = subprocess.run(
        ['pytest', '--collect-only', '-q', '--no-header'],
        capture_output=True,
        text=True,
        cwd='/Users/ethan/Documents/GitHub/SPMG3T7/backend'
    )

    for line in result.stdout.split('\n'):
        line = line.strip()
        if not line or 'warning' in line.lower() or '===' in line or 'collected' in line:
            continue

        # Parse: tests/test_file.py::TestClass::test_method
        # Or: tests/test_file.py::test_function
        match = re.match(r'(tests/[^:]+\.py)(?:::([^:]+))?::(.+)$', line)
        if not match:
            continue

        test_file = match.group(1)
        test_class = match.group(2) or ""
        test_name = match.group(3)

        # Build full test path
        if test_class:
            full_name = f"{test_class}::{test_name}"
        else:
            full_name = test_name

        test_type = classify_test(test_file, test_name, test_class)
        user_story = extract_user_story(test_file, test_name)
        feature = extract_feature(test_file, test_name)

        tests.append({
            'Test ID': f"BT{len(tests) + 1:04d}",
            'Test File': test_file,
            'Test Class': test_class,
            'Test Name': test_name,
            'Full Name': full_name,
            'Test Type': test_type,
            'User Story': user_story,
            'Feature': feature,
            'Category': 'Backend'
        })

    return tests

def collect_frontend_tests() -> List[Dict]:
    """Collect all frontend e2e tests."""
    tests = []
    frontend_path = Path('/Users/ethan/Documents/GitHub/SPMG3T7/frontend')
    e2e_path = frontend_path / 'e2e'

    if not e2e_path.exists():
        return tests

    # Find all .spec.ts files
    for spec_file in sorted(e2e_path.glob('**/*.spec.ts')):
        relative_path = spec_file.relative_to(frontend_path)

        # Read file to extract test names
        try:
            content = spec_file.read_text()

            # Find test() calls: test('description', async ({...}) => {
            test_matches = re.finditer(r"test\(['\"](.+?)['\"]\s*,", content)

            for match in test_matches:
                test_name = match.group(1)
                user_story = extract_user_story(str(spec_file), test_name)

                tests.append({
                    'Test ID': f"E2E{len(tests) + 1:04d}",
                    'Test File': str(relative_path),
                    'Test Class': "",
                    'Test Name': test_name,
                    'Full Name': test_name,
                    'Test Type': 'E2E',
                    'User Story': user_story,
                    'Feature': extract_feature(str(spec_file), test_name),
                    'Category': 'Frontend'
                })
        except Exception as e:
            print(f"Warning: Could not read {spec_file}: {e}")

    return tests

def generate_csv():
    """Generate comprehensive test inventory CSV."""
    print("Collecting backend tests...")
    backend_tests = collect_backend_tests()
    print(f"Collected {len(backend_tests)} backend tests")

    print("\nCollecting frontend e2e tests...")
    frontend_tests = collect_frontend_tests()
    print(f"Collected {len(frontend_tests)} frontend tests")

    all_tests = backend_tests + frontend_tests

    # Count by type
    unit_count = sum(1 for t in all_tests if t['Test Type'] == 'Unit')
    integration_count = sum(1 for t in all_tests if t['Test Type'] == 'Integration')
    e2e_count = sum(1 for t in all_tests if t['Test Type'] == 'E2E')

    print(f"\nTest breakdown:")
    print(f"  Unit: {unit_count} ({unit_count/len(all_tests)*100:.1f}%)")
    print(f"  Integration: {integration_count} ({integration_count/len(all_tests)*100:.1f}%)")
    print(f"  E2E: {e2e_count} ({e2e_count/len(all_tests)*100:.1f}%)")
    print(f"  Total: {len(all_tests)}")

    # Write CSV
    output_file = '/Users/ethan/Documents/GitHub/SPMG3T7/test_inventory.csv'
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'Test ID', 'Test Type', 'Category', 'User Story', 'Feature',
            'Test File', 'Test Class', 'Test Name', 'Full Name'
        ])
        writer.writeheader()
        writer.writerows(all_tests)

    print(f"\nCSV written to: {output_file}")
    return output_file

if __name__ == '__main__':
    generate_csv()
