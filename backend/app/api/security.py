from fastapi import Header, HTTPException, status
from typing import List, Optional

def get_current_role(x_user_role: Optional[str] = Header(default="customer")) -> str:
    """Extracts user role from X-User-Role header or defaults to 'customer'."""
    if not x_user_role:
        return "customer"
    return x_user_role.lower()

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = [r.lower() for r in allowed_roles]

    def __call__(self, x_user_role: Optional[str] = Header(default="customer")):
        role = (x_user_role or "customer").lower()
        if role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for role '{role}'. Required role(s): {', '.join(self.allowed_roles)}."
            )
        return role

require_analyst_or_admin = RoleChecker(["analyst", "admin"])
require_admin = RoleChecker(["admin"])
