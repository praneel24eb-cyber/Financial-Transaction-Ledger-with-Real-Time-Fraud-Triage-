import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from backend.app.config import settings
from backend.app.repositories.db import db_manager

logger = logging.getLogger(__name__)

SESSION_COOKIE = "ledger_session"
PBKDF2_ITERATIONS = 240_000

# Demo accounts created on startup (idempotent). Passwords are stored hashed,
# never in plaintext, so the login path exercises real credential verification.
DEMO_USERS = [
    {
        "username": "customer",
        "password": "customer123",
        "role": "customer",
        "display_name": "Demo Customer",
        "link_to_customer": True,
    },
    {
        "username": "analyst",
        "password": "analyst123",
        "role": "analyst",
        "display_name": "Fraud Analyst",
        "link_to_customer": False,
    },
    {
        "username": "admin",
        "password": "admin123",
        "role": "admin",
        "display_name": "Platform Admin",
        "link_to_customer": False,
    },
]


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """PBKDF2-HMAC-SHA256 password hash: pbkdf2_sha256$iterations$salt$digest."""
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(candidate.hex(), digest)
    except Exception:
        return False


def _sign(payload_b64: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def create_session_token(user: Dict[str, Any]) -> str:
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "name": user.get("display_name") or user["username"],
        "customer_id": user.get("customer_id"),
        "exp": int(time.time()) + settings.SESSION_MAX_AGE_SECONDS,
    }
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        .decode("utf-8")
        .rstrip("=")
    )
    return f"{payload_b64}.{_sign(payload_b64)}"


def decode_session_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Returns the session payload, or None for missing/forged/expired tokens."""
    if not token or "." not in token:
        return None

    payload_b64, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload_b64)):
        return None

    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Validates credentials against APP_USER. Returns the user row (without the hash) or None."""
    if not username or not password:
        return None

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, password_hash, role, customer_id, display_name "
                "FROM APP_USER WHERE LOWER(username) = LOWER(%s);",
                (username,),
            )
            row = cur.fetchone()

    if not row:
        return None

    if not verify_password(password, row["password_hash"]):
        return None

    user = dict(row)
    user.pop("password_hash", None)
    return user


def ensure_demo_users():
    """
    Idempotently creates the demo accounts used by the login portal.
    Safe to call on every startup and after a reseed.
    """
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MIN(customer_id) AS cid FROM CUSTOMER;")
            row = cur.fetchone()
            demo_customer_id = row["cid"] if row else None

            for spec in DEMO_USERS:
                cur.execute("SELECT 1 AS present FROM APP_USER WHERE username = %s;", (spec["username"],))
                if cur.fetchone():
                    if spec["link_to_customer"]:
                        cur.execute(
                            "UPDATE APP_USER SET customer_id = %s WHERE username = %s;",
                            (demo_customer_id, spec["username"]),
                        )
                    continue

                cur.execute(
                    """
                    INSERT INTO APP_USER (username, password_hash, role, customer_id, display_name, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW());
                    """,
                    (
                        spec["username"],
                        hash_password(spec["password"]),
                        spec["role"],
                        demo_customer_id if spec["link_to_customer"] else None,
                        spec["display_name"],
                    ),
                )
            conn.commit()

    logger.info("Demo login accounts ensured (customer / analyst / admin).")
