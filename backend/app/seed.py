"""Write the development accounts into Supabase.

Run once per environment, from `backend/`:

    python -m app.seed

Each account needs two records, because two systems own different halves of a
person (see `app.users`):

* one in `auth.users`, created through the Auth admin API, holding the password;
* one in `public.users`, holding the name and role this project cares about.

They are joined on email. Creating only one of them makes an account that cannot
sign in, so this script always does both.

Idempotent: an account that already exists has its password, name and role
brought back in line rather than being duplicated, so re-running after changing
SEED_PASSWORD is the supported way to reset it.

These are development credentials, documented in the README so the team can sign
in as each role. They are not secrets and must not be seeded into a deployed
environment — this is a script you run deliberately, not something that happens
on startup, precisely so that nobody creates them by accident.
"""

from supabase import AuthApiError, AuthError

from app import supabase_client, users
from app.config import seed_password
from app.permissions import Role

#: (email, display name, role). Matches the table documented in the README.
SEED_ACCOUNTS: tuple[tuple[str, str, Role], ...] = (
    ("organiser@spmg3t7.edu", "Dylan", Role.ORGANISER),
    ("coordinator@spmg3t7.edu", "Priya", Role.COORDINATOR),
)


def _upsert_auth_user(email: str, password: str) -> str:
    """Create the Auth account, or reset its password if it is already there.

    `email_confirm=True` because there is no inbox behind these addresses; an
    unconfirmed account cannot sign in, which would make the seed look like it
    had worked while nobody could actually get in.
    """
    admin = supabase_client.admin().auth.admin
    try:
        admin.create_user({"email": email, "password": password, "email_confirm": True})
    except (AuthApiError, AuthError):
        # Already registered. Find them and reset the password so a changed
        # SEED_PASSWORD takes effect rather than silently doing nothing.
        existing = next(
            (
                user
                for user in admin.list_users()
                if (user.email or "").lower() == email.lower()
            ),
            None,
        )
        if existing is None:
            raise
        admin.update_user_by_id(existing.id, {"password": password, "email_confirm": True})
        return f"reset auth password for {email}"
    return f"created auth account for {email}"


def _upsert_profile(email: str, name: str, role: Role) -> str:
    """Create or refresh the `public.users` row. Only existing columns are written."""
    client = supabase_client.admin()
    fields = {"email": email, "name": name, "role": str(role)}
    existing = (
        client.table(users.TABLE).select("id").ilike("email", email).limit(1).execute()
    )
    if existing.data:
        user_id = existing.data[0]["id"]
        client.table(users.TABLE).update(fields).eq("id", user_id).execute()
        return f"updated profile {email} (id {user_id}, {role})"

    created = client.table(users.TABLE).insert(fields).execute()
    user_id = created.data[0]["id"] if created.data else "?"
    return f"created profile {email} (id {user_id}, {role})"


def seed() -> list[str]:
    """Create or refresh each development account. Returns a line per step."""
    password = seed_password()
    report: list[str] = []
    for email, name, role in SEED_ACCOUNTS:
        report.append(_upsert_auth_user(email, password))
        report.append(_upsert_profile(email, name, role))
    return report


if __name__ == "__main__":
    for line in seed():
        print(line)
