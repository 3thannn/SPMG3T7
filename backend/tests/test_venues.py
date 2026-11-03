"""The venue endpoints — US9.1a-c, US9.2 and US9.3.

Four stories over one table, and the interesting part is that they do not share
a role. A Coordinator reads the catalogue (US9.2) and narrows it (US9.3); Venue
Staff create, update and delete the records in it (US9.1a-c). Neither role holds
the other half, so most of what is asserted here is a refusal.
"""

import pytest

#: A valid create payload. Individual tests override one field at a time, so a
#: failure names the field that broke rather than the whole request.
NEW_VENUE = {
    "name": "Atrium",
    "location": "Science Quarter",
    "capacity": 90,
    "facilities": "Natural light, cafe",
    "accessibilityFeatures": "Step-free access",
    "operatingHours": "08:00-18:00",
    "supportedLayouts": "Standing, seated rows",
}


def create(client, headers, **overrides) -> dict:
    """Create a venue and return it, failing the test if creation itself broke."""
    response = client.post("/venues", json={**NEW_VENUE, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


class TestListing:
    def test_a_coordinator_sees_the_catalogue(self, client, auth_headers):
        response = client.get("/venues", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 200, response.text
        venues = response.json()
        assert [venue["name"] for venue in venues] == [
            "Bertha Room",
            "Great Hall",
            "Seminar Room 4",
        ]







class TestOpeningOne:
    def test_a_coordinator_can_open_any_venue(self, client, auth_headers):
        response = client.get("/venues/1", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Great Hall"






class TestWhoMayWrite:
    """US9.1a-c are restricted to Venue Staff, and nobody else holds them.

    This used to assert 405 on the write verbs, because US9.2 had no write
    routes at all. The routes exist now, so the same rule is enforced one layer
    in: the verbs answer, and they answer 403 to everyone but Venue Staff.
    """

    def test_a_coordinator_cannot_create_a_venue(self, client, auth_headers):
        """A Coordinator reads the catalogue; maintaining it is a different job."""
        response = client.post("/venues", json=NEW_VENUE, headers=auth_headers("Event Coordinator"))

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["code"] == "forbidden"
        assert "Venue Staff" in detail["message"]

    def test_a_coordinator_cannot_update_a_venue(self, client, auth_headers):
        response = client.put(
            "/venues/1", json=NEW_VENUE, headers=auth_headers("Event Coordinator")
        )

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "forbidden"
        unchanged = client.get("/venues/1", headers=auth_headers("Event Coordinator")).json()
        assert unchanged["name"] == "Great Hall"

    def test_a_coordinator_cannot_delete_a_venue(self, client, auth_headers):
        response = client.delete("/venues/1", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "forbidden"
        still_there = client.get("/venues/1", headers=auth_headers("Event Coordinator"))
        assert still_there.status_code == 200







class TestCreating:
    """US9.1a: required name, capacity (positive integer) and location."""

    def test_venue_staff_can_add_a_venue(self, client, auth_headers):
        venue = create(client, auth_headers("Venue Staff"))

        assert venue["name"] == "Atrium"
        assert venue["location"] == "Science Quarter"
        assert venue["capacity"] == 90


    def test_the_optional_details_are_optional(self, client, auth_headers):
        """US9.1a names four optional fields; a venue without them is still valid."""
        venue = create(
            client,
            auth_headers("Venue Staff"),
            facilities="",
            accessibilityFeatures="",
            operatingHours="",
            supportedLayouts="",
        )

        assert venue["facilities"] == ""
        assert venue["accessibilityFeatures"] == ""
        assert venue["operatingHours"] == ""
        assert venue["supportedLayouts"] == ""

    def test_the_optional_details_are_kept_when_given(self, client, auth_headers):
        venue = create(
            client,
            auth_headers("Venue Staff"),
            facilities="Cafe, cloakroom",
            accessibilityFeatures="Step-free access",
            operatingHours="09:00-18:00",
            supportedLayouts="Standing, cabaret",
        )

        assert venue["facilities"] == "Cafe, cloakroom"
        assert venue["accessibilityFeatures"] == "Step-free access"
        assert venue["operatingHours"] == "09:00-18:00"
        assert venue["supportedLayouts"] == "Standing, cabaret"


    @pytest.mark.parametrize(
        ("change", "named"),
        [
            ({"name": ""}, "name"),
            ({"name": "   "}, "name"),
            ({"location": ""}, "location"),
            ({"location": "   "}, "location"),
            ({"capacity": None}, "capacity"),
            ({"capacity": 0}, "positive"),
            ({"capacity": -1}, "positive"),
        ],
    )
    def test_each_required_field_is_needed(
        self, client, auth_headers, venue_repository, change, named
    ):
        """US9.1a AC2: name, location and a positive whole capacity are required.

        One row per way a required field can be missing or wrong; capacity 0 is the
        boundary of "positive". A refused venue is not stored.
        """
        before = len(venue_repository.venues)
        payload = {**NEW_VENUE, **change}
        if change.get("capacity", 1) is None:
            del payload["capacity"]

        response = client.post("/venues", json=payload, headers=auth_headers("Venue Staff"))

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_venue"
        assert named in detail["message"].lower()
        assert len(venue_repository.venues) == before




    # --- Added: extra edge-case coverage for US9.1a/US9.1b ---





    # --- Added: extra edge-case coverage for US9.1a/US9.1b ---

    # --- Added: extra edge-case coverage for US9.1a/US9.1b ---





class TestUpdating:
    """US9.1b: any field editable except the system-generated ones."""


    def test_every_editable_field_actually_changes(self, client, auth_headers):
        response = client.put(
            "/venues/1",
            json={
                "name": "Great Hall Renamed",
                "location": "Main Campus, Building Z",
                "capacity": 321,
                "facilities": "New rig",
                "accessibilityFeatures": "Ramp",
                "operatingHours": "10:00-20:00",
                "supportedLayouts": "Theatre",
            },
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 200, response.text
        venue = response.json()
        assert venue["name"] == "Great Hall Renamed"
        assert venue["location"] == "Main Campus, Building Z"
        assert venue["capacity"] == 321
        assert venue["facilities"] == "New rig"
        assert venue["accessibilityFeatures"] == "Ramp"
        assert venue["operatingHours"] == "10:00-20:00"
        assert venue["supportedLayouts"] == "Theatre"

    def test_the_id_cannot_be_edited(self, client, auth_headers):
        """A system-generated field: sending one changes nothing."""
        response = client.put(
            "/venues/1",
            json={**NEW_VENUE, "name": "Great Hall", "id": "888"},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 200
        assert response.json()["id"] == "1"











class TestFiltering:
    """US9.3: narrow by capacity, location and accessibility, ANDed together.

    The fixture catalogue is built so no filter is a proxy for another — two
    venues share a location, two share an accessibility feature, and the
    capacities are far apart. A filter that quietly did nothing would therefore
    show up as the wrong row count rather than passing by coincidence.
    """

    def names(self, client, auth_headers, query: str = "") -> list[str]:
        response = client.get(f"/venues{query}", headers=auth_headers("Event Coordinator"))
        assert response.status_code == 200, response.text
        return [venue["name"] for venue in response.json()]



    def test_minimum_capacity_is_inclusive(self, client, auth_headers):
        """A venue holding exactly the number asked for holds the number asked for."""
        assert "Seminar Room 4" in self.names(client, auth_headers, "?minCapacity=60")





    def test_filters_combine_with_and_not_or(self, client, auth_headers):
        """The acceptance criterion, stated as a query.

        Library has two venues and minCapacity=50 has two venues, but only one
        venue is in both. OR would answer three.
        """
        assert self.names(client, auth_headers, "?location=Library&minCapacity=50") == [
            "Seminar Room 4"
        ]













