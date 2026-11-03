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

    US1.4 (Week 7): Event Coordinator Lead and Safety Officer join the active
    roles. Lead manages the unassigned queue (US8.2) and assigns Coordinators
    (US8.3). Safety Officer runs the Operational Safety Check (US17.x).

    Technical Support joins with the US19 equipment catalogue and request queue.
    Attendee joins with US20.1, registering for Confirmed events.
    """

    ORGANISER = "Event Organiser"
    COORDINATOR = "Event Coordinator"
    COORDINATOR_LEAD = "Event Coordinator Lead"
    VENUE_STAFF = "Venue Staff"
    SAFETY_OFFICER = "Safety Officer"
    TECH_SUPPORT = "Technical Support"
    ATTENDEE = "Attendee"


class Permission(StrEnum):
    """A single thing a role may do, named `resource:action`.

    Only permissions some role actually holds are listed. Declaring one before
    its story would put a name in the catalogue that nothing grants and nothing
    checks; each arrives with its own story.

    Note that reading the catalogue and maintaining it are separate permissions
    held by different roles: a Coordinator reads (US9.2) and Venue Staff write
    (US9.1a-c). Neither is a superset of the other, which is why there are four
    venue permissions rather than one.

    Requesting a venue for an event (US14.1) is a fifth, and not one of them:
    it does not change the catalogue, it asks Venue Staff for part of it.
    Cancelling one of those requests (US14.2) is the same grant rather than a
    sixth, as US12.1's blackouts are `venues:edit`: the same role holds both,
    under the same assignment rule, and a second name would only be one more
    thing for the frontend's copy to drift on.

    US1.4/US8.2/US8.3: Coordinator Lead permissions for managing assignments.
    US1.4/US17.x: Safety Officer permissions (placeholder for now).

    US4.4: the assigned Coordinator sends a ready event for its safety check
    (`safety:submit`), and the Safety Officer signs it off or sends it back
    (`safety:review`). Two names because two different roles hold them.

    US4.6: cancelling an event (`events:cancel`) is held by both the Organiser
    and the Coordinator, so neither role's existing grant could stand in for
    it. The role is the first half of the rule; owning the event, or being
    assigned to it, is the second, checked per event.

    US20.1: the assigned Coordinator turns registration on and sets the
    capacity (`registration:manage`), and an Attendee registers
    (`registrations:create`). Seeing which events are open is part of
    registering, so it is the same grant rather than a third.

    US20.3: who registered, with their names and emails, is for the owning
    Organiser and the assigned Coordinator (`registrations:read`). Its own
    permission because it is personal data: the Coordinator Lead reads every
    event (US8.6) but is not given the people registered for it.
    """

    EVENTS_CREATE = "events:create"
    EVENTS_READ_OWN = "events:read:own"
    EVENTS_READ_SUBMITTED = "events:read:submitted"
    EVENTS_READ_ALL = "events:read:all"  # US8.6: Lead sees all, not just assigned
    EVENTS_SUBMIT = "events:submit"
    EVENTS_REVIEW = "events:review"
    EVENTS_COMPLETE = "events:complete"
    EVENTS_CANCEL = "events:cancel"  # US4.6: owning Organiser or assigned Coordinator
    EVENTS_EDIT = "events:edit"
    EVENTS_CONFIRM = "events:confirm"  # US4.7: assigned Coordinator, once approved
    USERS_READ = "users:read"
    VENUES_READ = "venues:read"
    VENUES_CREATE = "venues:create"
    VENUES_EDIT = "venues:edit"
    VENUES_DELETE = "venues:delete"
    NOTIFICATIONS_READ = "notifications:read"
    BOOKINGS_REQUEST = "bookings:request"
    QUEUE_VIEW_UNASSIGNED = "queue:view:unassigned"  # US8.2: Lead sees unassigned queue
    COORDINATORS_ASSIGN = "coordinators:assign"  # US8.3: Lead assigns Coordinators
    SAFETY_REVIEW = "safety:review"  # US4.4/US17.x: Safety Officer decides the check
    SAFETY_SUBMIT = "safety:submit"  # US4.4: Coordinator sends a ready event for it
    HOLDS_PLACE = "holds:place"  # US14.3: Venue Staff keep a slot for a Coordinator
    BOOKINGS_DECIDE = "bookings:decide"  # US16.1: Venue Staff approve or reject requests
    EQUIPMENT_READ = "equipment:read"
    EQUIPMENT_WRITE = "equipment:write"
    EQUIPMENT_REQUEST = "equipment:request"
    EQUIPMENT_QUEUE = "equipment:queue"
    REGISTRATION_MANAGE = "registration:manage"  # US20.1: assigned Coordinator
    REGISTRATIONS_CREATE = "registrations:create"  # US20.1: Attendee
    REGISTRATIONS_READ = "registrations:read"  # US20.3: owning Organiser, assigned Coordinator


#: Said in the first person, to be dropped into a denial message.
PERMISSION_LABELS: dict[Permission, str] = {
    Permission.EVENTS_CREATE: "create events",
    Permission.EVENTS_READ_OWN: "view your own events",
    Permission.EVENTS_READ_SUBMITTED: "view submitted events",
    Permission.EVENTS_READ_ALL: "view all events",
    Permission.EVENTS_SUBMIT: "submit events for approval",
    Permission.EVENTS_REVIEW: "review submitted events",
    Permission.EVENTS_COMPLETE: "complete confirmed events",
    Permission.EVENTS_CANCEL: "cancel events",
    Permission.EVENTS_EDIT: "edit events",
    Permission.EVENTS_CONFIRM: "confirm events",
    Permission.USERS_READ: "view the user directory",
    Permission.VENUES_READ: "view the venue catalogue",
    Permission.VENUES_CREATE: "add a venue to the catalogue",
    Permission.VENUES_EDIT: "update a venue record",
    Permission.VENUES_DELETE: "remove a venue from the catalogue",
    Permission.NOTIFICATIONS_READ: "view and manage your notifications",
    Permission.BOOKINGS_REQUEST: "request and cancel venue bookings",
    Permission.QUEUE_VIEW_UNASSIGNED: "view the unassigned event queue",
    Permission.COORDINATORS_ASSIGN: "assign events to Coordinators",
    Permission.SAFETY_REVIEW: "review event safety",
    Permission.SAFETY_SUBMIT: "send events for a safety check",
    Permission.HOLDS_PLACE: "place tentative venue holds",
    Permission.BOOKINGS_DECIDE: "approve or reject venue booking requests",
    Permission.EQUIPMENT_READ: "view the equipment catalogue",
    Permission.EQUIPMENT_WRITE: "maintain equipment",
    Permission.EQUIPMENT_REQUEST: "request equipment for assigned events",
    Permission.EQUIPMENT_QUEUE: "review equipment requests",
    Permission.REGISTRATION_MANAGE: "open or close registration for events",
    Permission.REGISTRATIONS_CREATE: "register for events",
    Permission.REGISTRATIONS_READ: "see who has registered for events",
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ORGANISER: frozenset(
        {
            Permission.EVENTS_CREATE,
            Permission.EVENTS_READ_OWN,
            Permission.EVENTS_SUBMIT,
            # US4.6: cancel an event they own.
            Permission.EVENTS_CANCEL,
            # US10.1: told when a Coordinator moves one of their events.
            Permission.NOTIFICATIONS_READ,
            # US20.3: who registered for an event they own.
            Permission.REGISTRATIONS_READ,
        }
    ),
    Role.COORDINATOR: frozenset(
        {
            Permission.EVENTS_READ_SUBMITTED,
            Permission.EVENTS_REVIEW,
            Permission.EVENTS_COMPLETE,
            # US4.6: cancel an event assigned to them (US8.6, checked per event).
            Permission.EVENTS_CANCEL,
            Permission.EVENTS_EDIT,
            Permission.USERS_READ,
            Permission.VENUES_READ,
            # US14.1. The role is the first half of US8.6's rule; the event
            # being assigned to them is the second, checked per event.
            Permission.BOOKINGS_REQUEST,
            Permission.EQUIPMENT_READ,
            Permission.EQUIPMENT_REQUEST,
            # US4.4: Planning -> Pending Safety Check, on the events assigned
            # to them (US8.6, checked per event).
            Permission.SAFETY_SUBMIT,
            # US4.7: Pending Safety Check -> Confirmed, once every approval is
            # in, on the events assigned to them (US8.6, checked per event).
            Permission.EVENTS_CONFIRM,
            # US10.2: told about assignments and booking or safety problems.
            Permission.NOTIFICATIONS_READ,
            # US20.1: registration on the events assigned to them (US8.6).
            Permission.REGISTRATION_MANAGE,
            # US20.3: who registered for the events assigned to them.
            Permission.REGISTRATIONS_READ,
        }
    ),
    # US1.4/US8.2/US8.3: Coordinator Lead manages the unassigned queue and
    # assigns events to Coordinators. Can view all events (US8.6), not just
    # assigned ones like regular Coordinators.
    Role.COORDINATOR_LEAD: frozenset(
        {
            Permission.EVENTS_READ_ALL,
            Permission.USERS_READ,
            Permission.VENUES_READ,
            Permission.QUEUE_VIEW_UNASSIGNED,
            Permission.COORDINATORS_ASSIGN,
            Permission.EQUIPMENT_READ,
            # US10.3: told when a submitted event lands in the unassigned queue.
            Permission.NOTIFICATIONS_READ,
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
            # US14.3: tentative holds, which expire on their own.
            Permission.HOLDS_PLACE,
            # US16.1: only Venue Staff confirm or turn down a booking request.
            Permission.BOOKINGS_DECIDE,
            # US4.6: told when an event's bookings are released by its cancellation.
            Permission.NOTIFICATIONS_READ,
        }
    ),
    # US1.4: Safety Officer. US4.4 lets them read and decide events that are
    # Pending Safety Check; the queue and detail view grow in US17.1/US17.2.
    Role.SAFETY_OFFICER: frozenset(
        {
            Permission.SAFETY_REVIEW,
        }
    ),
    Role.TECH_SUPPORT: frozenset(
        {
            Permission.EQUIPMENT_READ,
            Permission.EQUIPMENT_WRITE,
            Permission.EQUIPMENT_QUEUE,
            Permission.NOTIFICATIONS_READ,
        }
    ),
    # US20.1: Attendees see the Confirmed events taking registrations and
    # register for them, and hold nothing else: no event, venue or planning
    # permission, so the internal pages are not theirs.
    Role.ATTENDEE: frozenset(
        {
            Permission.REGISTRATIONS_CREATE,
            # US4.6: told when an event they registered for is cancelled.
            Permission.NOTIFICATIONS_READ,
        }
    ),
}

#: Where each role lands after signing in — the "role-appropriate view" of
#: US1.1. Venue Staff are the role that made this lookup earn its keep: the
#: events list is no use to someone who cannot open an event, so they land on
#: the catalogue they maintain instead.
#:
#: US1.4 AC2: Lead lands on the unassigned queue (US8.2), Safety Officer lands
#: on the safety review queue (US17.1, placeholder for now).
HOME_ROUTE: dict[Role, str] = {
    Role.ORGANISER: "/events",
    Role.COORDINATOR: "/events",
    Role.COORDINATOR_LEAD: "/unassigned-queue",
    Role.VENUE_STAFF: "/venues",
    Role.SAFETY_OFFICER: "/safety-review",
    Role.TECH_SUPPORT: "/equipment-requests",
    Role.ATTENDEE: "/attend",
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
