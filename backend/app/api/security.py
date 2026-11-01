from typing import List, Optional
from urllib.parse import quote

from fastapi import Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from backend.app.services.auth_service import SESSION_COOKIE, decode_session_token
from backend.app.config import settings

# Roles that may act on money movement / read account data
CUSTOMER_ROLES = ["customer", "admin"]
# Roles that may triage fraud alerts
ANALYST_ROLES = ["analyst", "admin"]
# Roles that may inspect audit / infrastructure data
ADMIN_ROLES = ["admin"]


def get_session_user(request: Request) -> Optional[dict]:
    """Decodes the signed session cookie, returning None when absent/forged/expired."""
    return decode_session_token(request.cookies.get(SESSION_COOKIE))


def resolve_role(request: Request, x_user_role: Optional[str] = None) -> Optional[str]:
    """
    Role resolution order:
      1. X-User-Role header, only when ALLOW_ROLE_HEADER is enabled (service clients)
      2. Signed session cookie (browser UI)
      3. None -> unauthenticated
    """
    if x_user_role and settings.ALLOW_ROLE_HEADER:
        return x_user_role.lower()
    user = get_session_user(request)
    if user and user.get("role"):
        return str(user["role"]).lower()
    return None


def get_current_role(
    request: Request, x_user_role: Optional[str] = Header(default=None)
) -> str:
    """Returns the effective role, defaulting to 'anonymous' when unauthenticated."""
    return resolve_role(request, x_user_role) or "anonymous"


def session_customer_id(request: Request) -> Optional[int]:
    """
    Customer ID bound to a browser session, used for row-level scoping.

    Returns None when the caller is not a session-authenticated customer, which
    includes staff sessions and trusted header-based service clients (X-User-Role).
    """
    user = get_session_user(request)
    if user and str(user.get("role", "")).lower() == "customer":
        return user.get("customer_id")
    return None


class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = [r.lower() for r in allowed_roles]

    def __call__(
        self, request: Request, x_user_role: Optional[str] = Header(default=None)
    ) -> str:
        role = resolve_role(request, x_user_role)

        if role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Sign in at /login or provide an X-User-Role header.",
                headers={"WWW-Authenticate": "Session"},
            )

        if role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for role '{role}'. Required role(s): {', '.join(self.allowed_roles)}.",
            )
        return role


require_analyst_or_admin = RoleChecker(ANALYST_ROLES)
require_admin = RoleChecker(ADMIN_ROLES)
require_customer_or_admin = RoleChecker(CUSTOMER_ROLES)


def page_guard(request: Request, allowed_roles: List[str]) -> Optional[RedirectResponse]:
    """
    Server-side gate for HTML routes. Returns a redirect response when the visitor may not
    render the page, otherwise None.
    """
    user = get_session_user(request)
    next_url = quote(str(request.url.path), safe="/")

    if not user:
        return RedirectResponse(url=f"/login?next={next_url}", status_code=status.HTTP_303_SEE_OTHER)

    if str(user.get("role", "")).lower() not in [r.lower() for r in allowed_roles]:
        return RedirectResponse(url="/?denied=1", status_code=status.HTTP_303_SEE_OTHER)

    return None


def home_for_role(role: Optional[str]) -> str:
    """Landing page per role, so nobody lands on a page they cannot use."""
    if role == "analyst":
        return "/ui/alerts"
    if role == "admin":
        return "/"
    return "/"
