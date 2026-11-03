"""US1.4: the Coordinator Lead and Safety Officer roles.

AC1 and AC2 (each role exists, signs in and lands on its own view) are proved by
`test_auth_login.py::test_each_role_is_told_where_its_own_view_is`, which covers
every role. This file holds AC3: US1.3's access rule applies to both new roles.
"""

import pytest

from tests.test_events import DRAFT


@pytest.mark.parametrize("role", ["Event Coordinator Lead", "Safety Officer"])
def test_the_new_roles_are_refused_out_of_role_with_the_reason(client, auth_headers, role):
    """Neither role creates event requests; that is the Organiser's work."""
    response = client.post("/events", json=DRAFT, headers=auth_headers(role))

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "forbidden"
    assert detail["message"].startswith(f"The {role} role cannot ")
    assert "Event Organiser" in detail["message"]
