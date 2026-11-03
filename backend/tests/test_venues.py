"""The venue endpoints — US9.1a-c, US9.2 and US9.3.

Four stories over one table, and the interesting part is that they do not share
a role. A Coordinator reads the catalogue (US9.2) and narrows it (US9.3); Venue
Staff create, update and delete the records in it (US9.1a-c). Neither role holds
the other half, so most of what is asserted here is a refusal.
"""

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

    def test_the_catalogue_is_ordered_by_name(self, client, auth_headers):
        """Alphabetical, not insertion order — the fixture is deliberately not."""
        response = client.get("/venues", headers=auth_headers("Event Coordinator"))

        names = [venue["name"] for venue in response.json()]
        assert names == sorted(names)

    def test_a_venue_carries_the_details_a_coordinator_needs(self, client, auth_headers):
        response = client.get("/venues", headers=auth_headers("Event Coordinator"))

        hall = next(v for v in response.json() if v["name"] == "Great Hall")
        assert hall["location"] == "Main Campus, Building A"
        assert hall["capacity"] == 500
        assert hall["facilities"] == "Stage, PA system, projector"
        assert hall["accessibilityFeatures"] == "Step-free access, hearing loop"
        assert hall["operatingHours"] == "08:00-22:00"

    def test_ids_go_out_as_strings(self, client, auth_headers):
        response = client.get("/venues", headers=auth_headers("Event Coordinator"))

        assert all(isinstance(venue["id"], str) for venue in response.json())

    def test_unrecorded_details_come_back_empty_rather_than_null(self, client, auth_headers):
        """The columns are nullable; the client renders a string either way."""
        response = client.get("/venues", headers=auth_headers("Event Coordinator"))

        room = next(v for v in response.json() if v["name"] == "Bertha Room")
        assert room["facilities"] == ""
        assert room["accessibilityFeatures"] == ""
        assert room["operatingHours"] == ""

    def test_an_empty_catalogue_is_an_empty_list_not_an_error(
        self, client, auth_headers, venue_repository
    ):
        venue_repository.venues = []

        response = client.get("/venues", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 200
        assert response.json() == []


class TestOpeningOne:
    def test_a_coordinator_can_open_any_venue(self, client, auth_headers):
        response = client.get("/venues/1", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Great Hall"

    def test_a_venue_that_does_not_exist_is_a_404(self, client, auth_headers):
        response = client.get("/venues/9999", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "venue_not_found"

    def test_an_id_that_is_not_a_number_is_a_404_not_a_500(self, client, auth_headers):
        response = client.get("/venues/abc", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 404


class TestWhoMayLook:
    def test_an_organiser_cannot_see_the_catalogue(self, client, auth_headers):
        """US9.2 is a Coordinator's story. The Organiser role does not hold it."""
        response = client.get("/venues", headers=auth_headers("Event Organiser"))

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["code"] == "forbidden"
        # US1.3: the refusal says what was refused and who may do it.
        assert "venue catalogue" in detail["message"]
        assert "Event Coordinator" in detail["message"]

    def test_an_organiser_cannot_open_a_venue_either(self, client, auth_headers):
        response = client.get("/venues/1", headers=auth_headers("Event Organiser"))

        assert response.status_code == 403

    def test_signing_out_is_enough_to_lose_access(self, client, auth_headers):
        headers = auth_headers("Event Coordinator")
        client.post("/auth/logout", headers=headers)

        assert client.get("/venues", headers=headers).status_code == 401

    def test_the_catalogue_needs_a_session(self, client):
        assert client.get("/venues").status_code == 401

    def test_a_venue_needs_a_session(self, client):
        """And says nothing about whether that venue exists."""
        assert client.get("/venues/1").status_code == 401


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

    def test_a_coordinator_cannot_delete_a_venue(self, client, auth_headers):
        response = client.delete("/venues/1", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 403

    def test_an_organiser_cannot_write_either(self, client, auth_headers):
        headers = auth_headers("Event Organiser")

        assert client.post("/venues", json=NEW_VENUE, headers=headers).status_code == 403
        assert client.put("/venues/1", json=NEW_VENUE, headers=headers).status_code == 403
        assert client.delete("/venues/1", headers=headers).status_code == 403

    def test_writing_needs_a_session_at_all(self, client):
        assert client.post("/venues", json=NEW_VENUE).status_code == 401
        assert client.put("/venues/1", json=NEW_VENUE).status_code == 401
        assert client.delete("/venues/1").status_code == 401

    def test_venue_staff_cannot_reach_the_events_list(self, client, auth_headers):
        """The permission goes one way: the catalogue is not a door into events."""
        response = client.get("/events", headers=auth_headers("Venue Staff"))

        assert response.status_code == 403

    def test_venue_staff_can_read_the_catalogue_they_maintain(self, client, auth_headers):
        """Maintaining a record means finding it first."""
        response = client.get("/venues", headers=auth_headers("Venue Staff"))

        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_venue_staff_cannot_read_the_user_directory(self, client, auth_headers):
        """A write permission on one table is not a general elevation."""
        response = client.get("/auth/users", headers=auth_headers("Venue Staff"))

        assert response.status_code == 403


class TestCreating:
    """US9.1a: required name, capacity (positive integer) and location."""

    def test_venue_staff_can_add_a_venue(self, client, auth_headers):
        venue = create(client, auth_headers("Venue Staff"))

        assert venue["name"] == "Atrium"
        assert venue["location"] == "Science Quarter"
        assert venue["capacity"] == 90

    def test_a_created_venue_appears_in_the_catalogue(self, client, auth_headers):
        create(client, auth_headers("Venue Staff"))

        listed = client.get("/venues", headers=auth_headers("Event Coordinator")).json()

        assert "Atrium" in [venue["name"] for venue in listed]

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

    def test_the_new_venue_carries_its_own_id_and_timestamps(self, client, auth_headers):
        venue = create(client, auth_headers("Venue Staff"))

        assert isinstance(venue["id"], str)
        assert venue["createdAt"]
        assert venue["updatedAt"]

    def test_a_name_is_required(self, client, auth_headers):
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "name": ""},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_venue"
        assert "name" in detail["message"]

    def test_a_name_of_only_spaces_is_no_name(self, client, auth_headers):
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "name": "   "},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 400

    def test_a_location_is_required(self, client, auth_headers):
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "location": ""},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 400
        assert "location" in response.json()["detail"]["message"]

    # --- Added: extra edge-case coverage for US9.1a/US9.1b ---
    def test_a_location_of_only_spaces_is_no_location(self, client, auth_headers):
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "location": "   "},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 400
        assert "location" in response.json()["detail"]["message"]

    def test_a_capacity_is_required(self, client, auth_headers):
        response = client.post(
            "/venues",
            json={k: v for k, v in NEW_VENUE.items() if k != "capacity"},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 400
        assert "capacity" in response.json()["detail"]["message"].lower()

    def test_a_capacity_must_be_positive(self, client, auth_headers):
        """US9.1a says positive, so nought is refused as well as a negative."""
        for capacity in (0, -1, -500):
            response = client.post(
                "/venues",
                json={**NEW_VENUE, "capacity": capacity},
                headers=auth_headers("Venue Staff"),
            )

            assert response.status_code == 400, capacity
            assert "positive" in response.json()["detail"]["message"]

    def test_a_capacity_that_is_not_a_whole_number_is_refused(self, client, auth_headers):
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "capacity": "many"},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code in (400, 422)

    def test_an_overlong_name_is_refused_with_a_sentence(self, client, auth_headers):
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "name": "x" * 256},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 400
        assert "255" in response.json()["detail"]["message"]

    # --- Added: extra edge-case coverage for US9.1a/US9.1b ---
    def test_an_overlong_location_is_refused_with_a_sentence(self, client, auth_headers):
        """`venues.location` is VARCHAR(500) — the same story as an overlong name."""
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "location": "x" * 501},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 400
        assert "500" in response.json()["detail"]["message"]

    # --- Added: extra edge-case coverage for US9.1a/US9.1b ---
    def test_a_capacity_beyond_what_postgres_can_store_is_refused(self, client, auth_headers):
        """CAPACITY_MAX exists so this is a sentence, not a raw 500 from the driver."""
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "capacity": 2_147_483_648},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 400
        assert "larger than any venue" in response.json()["detail"]["message"]

    def test_a_duplicate_name_is_a_conflict_not_a_crash(self, client, auth_headers):
        """The name column is UNIQUE, so the second one is refused by a rule."""
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "name": "Great Hall"},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "venue_name_taken"
        assert "Great Hall" in detail["message"]

    def test_surrounding_space_is_trimmed_from_the_fields(self, client, auth_headers):
        venue = create(
            client,
            auth_headers("Venue Staff"),
            name="  Atrium  ",
            location="  Science Quarter  ",
        )

        assert venue["name"] == "Atrium"
        assert venue["location"] == "Science Quarter"

    def test_an_id_in_the_request_is_ignored(self, client, auth_headers):
        """The id is system-generated, so sending one must not choose it."""
        venue = create(client, auth_headers("Venue Staff"), id="999")

        assert venue["id"] != "999"


class TestUpdating:
    """US9.1b: any field editable except the system-generated ones."""

    def test_venue_staff_can_change_a_venue(self, client, auth_headers):
        response = client.put(
            "/venues/1",
            json={**NEW_VENUE, "name": "Great Hall", "capacity": 450},
            headers=auth_headers("Venue Staff"),
        )

        assert response.status_code == 200, response.text
        assert response.json()["capacity"] == 450

