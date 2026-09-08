"""What each role may do — the baseline access rules behind US1.3.

One catalogue, read by the dependency that guards a route and by the payload
the frontend uses to decide what to offer. The frontend keeps a copy so it can
hide what a user cannot do, but this module is the enforcement point: a hidden
button is a courtesy, a refused request is the rule.
"""

from enum import StrEnum


class Role(StrEnum):
    """The roles the system knows about. The values are the wire format.

    Scoped to the two roles that have features: an Organiser proposes events, a
    Coordinator reviews them. Venue Staff, Technical Support and Attendee are
    part of the wider plan and are deliberately not modelled yet — a role that
    can sign in but can do nothing is a dead end for whoever holds it. They come
    back with the epics that give them something to do.
    """

    ORGANISER = "Organiser"
    COORDINATOR = "Coordinator"


class Permission(StrEnum):
    """A single thing a role may do, named `resource:action`.

    Only permissions some role actually holds are listed. Declaring the ones for
    venue booking or registration now would put names in the catalogue that
    nothing grants and nothing checks; they arrive with their own roles.
    """

    EVENTS_CREATE = "events:create"
    EVENTS_READ_OWN = "events:read:own"
    EVENTS_READ_ALL = "events:read:all"
    EVENTS_SUBMIT = "events:submit"
    EVENTS_REVIEW = "events:review"
    USERS_READ = "users:read"


#: Said in the first person, to be dropped into a denial message.
PERMISSION_LABELS: dict[Permission, str] = {
    Permission.EVENTS_CREATE: "create events",
    Permission.EVENTS_READ_OWN: "view your own events",
    Permission.EVENTS_READ_ALL: "view every event",
    Permission.EVENTS_SUBMIT: "submit events for approval",
    Permission.EVENTS_REVIEW: "review submitted events",
    Permission.USERS_READ: "view the user directory",
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ORGANISER: frozenset(
        {
            Permission.EVENTS_CREATE,
            Permission.EVENTS_READ_OWN,
            Permission.EVENTS_SUBMIT,
        }
    ),
    Role.COORDINATOR: frozenset(
        {
            Permission.EVENTS_READ_ALL,
            Permission.EVENTS_REVIEW,
            Permission.USERS_READ,
        }
    ),
}

#: Where each role lands after signing in — the "role-appropriate view" of
#: US1.1. Both roles work from the events list today, so both point at it. The
#: lookup stays because the answer stops being the same as soon as a role with
#: its own workspace arrives, and the client already reads its landing from here
#: rather than deciding for itself.
HOME_ROUTE: dict[Role, str] = {
    Role.ORGANISER: "/events",
    Role.COORDINATOR: "/events",
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
