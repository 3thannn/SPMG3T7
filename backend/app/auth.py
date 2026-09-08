"""Authentication and authorisation routes — US1.1, US1.2 and US1.3.

Errors carry a machine-readable `code` alongside their message so the client can
tell the three ways a request can be turned away apart: credentials that were
wrong, a session that has lapsed, and a role that is not allowed. They read the
same to a careless client and very differently to a careful one.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app import users
from app.config import session_idle_minutes
from app.permissions import HOME_ROUTE, Permission, Role, denial_message, has_permission
from app.sessions import SessionState, SessionStore
from app.users import User

router = APIRouter(prefix="/auth", tags=["auth"])

store = SessionStore(idle_timeout=timedelta(minutes=session_idle_minutes()))

# auto_error=False so a missing header reaches our own handler and produces the
# same error shape as every other refusal.
_bearer = HTTPBearer(auto_error=False, description="Session token from /auth/login")


class ErrorCode:
    INVALID_CREDENTIALS = "invalid_credentials"
    NOT_AUTHENTICATED = "not_authenticated"
    SESSION_EXPIRED = "session_expired"
    FORBIDDEN = "forbidden"


def _unauthorised(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


class LoginRequest(BaseModel):
    email: str
    password: str


class Identity(BaseModel):
    """Who the caller is and what they may do — the shape the client stores."""

    id: str
    email: str
    name: str
    role: Role
    permissions: list[Permission]
    home: str
    idle_minutes: int = Field(serialization_alias="idleMinutes")


class SessionResponse(Identity):
    token: str


def _identity_fields(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        # Sorted so the payload is stable between requests and easy to assert on.
        "permissions": sorted(user.permissions, key=str),
        "home": HOME_ROUTE.get(user.role, "/home"),
        "idle_minutes": int(store.idle_timeout.total_seconds() // 60),
    }


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Resolve the bearer token to a user, extending the session as it goes."""
    if credentials is None or not credentials.credentials:
        raise _unauthorised(ErrorCode.NOT_AUTHENTICATED, "Sign in to continue.")

    state, session = store.touch(credentials.credentials)
    if state is SessionState.EXPIRED:
        raise _unauthorised(
            ErrorCode.SESSION_EXPIRED,
            "Your session expired after a period of inactivity. Sign in again to continue.",
        )
    if session is None:
        raise _unauthorised(ErrorCode.NOT_AUTHENTICATED, "Your session is no longer valid.")

    user = users.get_by_id(session.user_id)
    if user is None:
        # The account went away underneath a live session; the session is void.
        store.revoke(credentials.credentials)
        raise _unauthorised(ErrorCode.NOT_AUTHENTICATED, "Your account is no longer active.")

    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_permission(permission: Permission):
    """Guard a route with one permission (US1.3).

    Use as `Depends(require_permission(Permission.EVENTS_REVIEW))`. A caller
    without it gets 403 and a message naming what was refused and who may do it,
    rather than a bare "forbidden".
    """

    def dependency(user: CurrentUser) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": ErrorCode.FORBIDDEN,
                    "message": denial_message(user.role, permission),
                    "required": str(permission),
                    "role": str(user.role),
                },
            )
        return user

    return dependency


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest) -> SessionResponse:
    """US1.1: exchange credentials for a session and a role-appropriate landing."""
    user = users.authenticate(payload.email, payload.password)
    if user is None:
        # One message for both a wrong password and an unknown address, so the
        # form cannot be used to find out who has an account.
        raise _unauthorised(ErrorCode.INVALID_CREDENTIALS, "Incorrect email or password.")

    session = store.create(user.id)
    return SessionResponse(token=session.token, **_identity_fields(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Response:
    """US1.2: end the session now, so the token stops working immediately.

    Succeeds whether or not the token was still live — signing out twice, or
    with a session that already expired, leaves the caller signed out either
    way, and saying so tells an attacker which tokens are real.
    """
    if credentials is not None and credentials.credentials:
        store.revoke(credentials.credentials)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=Identity)
def me(user: CurrentUser) -> Identity:
    """Who the caller is. The client calls this on load to restore a session."""
    return Identity(**_identity_fields(user))


class DirectoryEntry(BaseModel):
    id: str
    name: str
    email: str
    role: Role


@router.get("/users", response_model=list[DirectoryEntry])
def directory(
    _: Annotated[User, Depends(require_permission(Permission.USERS_READ))],
) -> list[DirectoryEntry]:
    """The user directory, restricted to Coordinators.

    The first route to sit behind `require_permission`, and the one that makes
    US1.3 demonstrable end to end: sign in as Venue Staff, call this, get a 403
    that explains itself. Coordinator Assignment will be its real consumer.
    """
    return [
        DirectoryEntry(id=user.id, name=user.name, email=user.email, role=user.role)
        for user in users.list_users()
    ]
