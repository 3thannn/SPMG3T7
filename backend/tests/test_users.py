"""The user directory, and what it does with rows it cannot use.

A person is two records: the credential in `auth.users`, owned by Supabase, and
the profile in `public.users`, owned by this project, joined on email. That join
can be half-made in either direction, and both halves are states this code has
to answer for rather than crash on.
"""

from app.permissions import Permission, Role
from app.users import InMemoryUsers, User, to_user

ROW = {"id": 1, "email": "organiser@spmg3t7.edu", "name": "Dylan", "role": "Event Organiser"}


class TestReadingARow:
    def test_a_modelled_role_becomes_a_user(self):
        user = to_user(ROW)

        assert user is not None
        assert user.id == 1
        assert user.role is Role.ORGANISER
        assert Permission.EVENTS_CREATE in user.permissions

    def test_an_unmodelled_role_is_skipped_not_raised(self):
        """Every `user_role` value is modelled since US20.1, so this is a made-up one."""
        for role in ("Caterer",):
            assert to_user({**ROW, "role": role}) is None

    def test_venue_staff_became_a_modelled_role_with_us9_1(self):
        """It was skipped until there were venue records to maintain."""
        user = to_user({**ROW, "role": "Venue Staff"})

        assert user is not None
        assert user.role is Role.VENUE_STAFF
        assert Permission.VENUES_CREATE in user.permissions

    def test_attendee_became_a_modelled_role_with_us20_1(self):
        """It was skipped until there were events to register for."""
        user = to_user({**ROW, "role": "Attendee"})

        assert user is not None
        assert user.role is Role.ATTENDEE
        # US4.6 added notifications:read, for an event they registered for being cancelled.
        assert user.permissions == {Permission.REGISTRATIONS_CREATE, Permission.NOTIFICATIONS_READ}

    def test_one_unusable_row_does_not_take_the_directory_with_it(self):
        rows = [ROW, {**ROW, "id": 2, "email": "a@spmg3t7.edu", "role": "Caterer"}]

        usable = [user for user in (to_user(row) for row in rows) if user is not None]

        assert [user.id for user in usable] == [1]


class TestAuthenticating:
    """The credential and the profile are separate, so either can be missing."""

    def build(self) -> InMemoryUsers:
        return InMemoryUsers(
            users=[User(id=1, email="organiser@spmg3t7.edu", name="Dylan", role=Role.ORGANISER)],
            passwords={"organiser@spmg3t7.edu": "Sprint1!demo"},
        )

    def test_the_right_password_returns_the_profile(self):
        found = self.build().authenticate("organiser@spmg3t7.edu", "Sprint1!demo")

        assert found is not None
        assert found.name == "Dylan"

    def test_a_wrong_password_is_refused(self):
        assert self.build().authenticate("organiser@spmg3t7.edu", "wrong") is None

    def test_an_address_with_no_credential_is_refused(self):
        """A profile row with no Auth account has nothing to prove itself with."""
        store = self.build()
        store.passwords.clear()

        assert store.authenticate("organiser@spmg3t7.edu", "Sprint1!demo") is None

    def test_a_credential_with_no_profile_is_refused(self):
        """Proving who you are is not enough: without a row we do not know your role."""
        store = self.build()
        store.users.clear()

        assert store.authenticate("organiser@spmg3t7.edu", "Sprint1!demo") is None

    def test_the_address_is_matched_case_insensitively(self):
        found = self.build().authenticate("  Organiser@SPMG3T7.edu ", "Sprint1!demo")

        assert found is not None
