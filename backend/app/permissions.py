"""What each role may do — the baseline access rules behind US1.3.

One catalogue, read by the dependency that guards a route and by the payload
the frontend uses to decide what to offer. The frontend keeps a copy so it can
hide what a user cannot do, but this module is the enforcement point: a hidden
button is a courtesy, a refused request is the rule.
"""

from collections.abc import Iterable
from enum import StrEnum


class Role(StrEnum):
    """The roles the system knows about. The values are the wire format.

    The three roles that have features: an Organiser proposes events, a
    Coordinator reviews them and reads the venue catalogue, and Venue Staff
    maintain that catalogue (US9.1a-c).

    Technical Support and Attendee are still deliberately absent — a role that
    can sign in but can do nothing is a dead end for whoever holds it. They come
    back with the epics that give them something to do, which is exactly how
    Venue Staff arrived: it was unmodelled until there were venue records to
    create, update and delete.
    """

    ORGANISER = "Event Organiser"
    COORDINATOR = "Event Coordinator"
    VENUE_STAFF = "Venue Staff"


class Permission(StrEnum):
    """A single thing a role may do, named `resource:action`.

    Only permissions some role actually holds are listed. Declaring the ones for
    venue booking or registration now would put names in the catalogue that
    nothing grants and nothing checks; they arrive with their own roles.

    Note that reading the catalogue and maintaining it are separate permissions
    held by different roles: a Coordinator reads (US9.2) and Venue Staff write
    (US9.1a-c). Neither is a superset of the other, which is why there are four
    venue permissions rather than one.
    """

    EVENTS_CREATE = "events:create"
    EVENTS_READ_OWN = "events:read:own"
    EVENTS_READ_SUBMITTED = "events:read:submitted"
    EVENTS_SUBMIT = "events:submit"
    EVENTS_REVIEW = "events:review"
    EVENTS_EDIT = "events:edit"
    USERS_READ = "users:read"
    VENUES_READ = "venues:read"
    VENUES_CREATE = "venues:create"
    VENUES_EDIT = "venues:edit"
    VENUES_DELETE = "venues:delete"
    NOTIFICATIONS_READ = "notifications:read"


#: Said in the first person, to be dropped into a denial message.
PERMISSION_LABELS: dict[Permission, str] = {
    Permission.EVENTS_CREATE: "create events",
    Permission.EVENTS_READ_OWN: "view your own events",
    Permission.EVENTS_READ_SUBMITTED: "view submitted events",
    Permission.EVENTS_SUBMIT: "submit events for approval",
    Permission.EVENTS_REVIEW: "review submitted events",
    Permission.EVENTS_EDIT: "edit events",
    Permission.USERS_READ: "view the user directory",
    Permission.VENUES_READ: "view the venue catalogue",
    Permission.VENUES_CREATE: "add a venue to the catalogue",
    Permission.VENUES_EDIT: "update a venue record",
    Permission.VENUES_DELETE: "remove a venue from the catalogue",
    Permission.NOTIFICATIONS_READ: "view and manage your notifications",
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ORGANISER: frozenset(
        {
            Permission.EVENTS_CREATE,
            Permission.EVENTS_READ_OWN,
            Permission.EVENTS_SUBMIT,
            # US10.1: told when a Coordinator moves one of their events.
            Permission.NOTIFICATIONS_READ,
        }
    ),
    Role.COORDINATOR: frozenset(
        {
            Permission.EVENTS_READ_SUBMITTED,
            Permission.EVENTS_REVIEW,
            Permission.EVENTS_EDIT,
            Permission.USERS_READ,
            Permission.VENUES_READ,
        }
    ),
    # US9.1a-c: Venue Staff own the catalogue and nothing else. They read it
    # because maintaining a record means finding it first; they hold no event
    # permission, so the events screens are not theirs.
    Role.VENUE_STAFF: frozenset(
        {
            Permission.VENUES_READ,
            Permission.VENUES_CREATE,
            Permission.VENUES_EDIT,
            Permission.VENUES_DELETE,
        }
    ),
}

#: Where each role lands after signing in — the "role-appropriate view" of
#: US1.1. Venue Staff are the role that made this lookup earn its keep: the
#: events list is no use to someone who cannot open an event, so they land on
#: the catalogue they maintain instead.
HOME_ROUTE: dict[Role, str] = {
    Role.ORGANISER: "/events",
    Role.COORDINATOR: "/events",
    Role.VENUE_STAFF: "/venues",
}


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in permissions_for(role)


def roles_with(permission: Permission) -> list[Role]:
    """Which roles hold a permission, in the order the roles are declared."""
    return [role for role in Role if permission in permissions_for(role)]


def denial_message(role: Role, permission: Permission) -> str:
    """US1.3: say what was refused and who may do it, not just "forbidden"."""
    action = PERMISSION_LABELS.get(permission, str(permission))
    allowed = roles_with(permission)
    if not allowed:
        return f"The {role} role cannot {action}. That is not available to any role yet."
    return (
        f"The {role} role cannot {action}. "
        f"That is available to: {', '.join(str(item) for item in allowed)}."
    )


def roles_with_any(permissions: "Iterable[Permission]") -> list[Role]:
    """Which roles hold at least one of these, in the order the roles are declared."""
    wanted = set(permissions)
    return [role for role in Role if wanted & permissions_for(role)]


def denial_message_any(role: Role, permissions: "Iterable[Permission]") -> str:
    """The US1.3 denial for a route that more than one permission can open.

    The events list is the case that needs it: an Organiser reaches it through
    events:read:own and a Coordinator through events:read:submitted, so naming a
    single required permission would misdescribe the rule to one of them.
    """
    wanted = list(permissions)
    actions = " or ".join(PERMISSION_LABELS.get(item, str(item)) for item in wanted)
    allowed = roles_with_any(wanted)
    if not allowed:
        return f"The {role} role cannot {actions}. That is not available to any role yet."
    return (
        f"The {role} role cannot {actions}. "
        f"That is available to: {', '.join(str(item) for item in allowed)}."
    )
