from typing import List
from fastapi import APIRouter, HTTPException, status, Depends, Request
from backend.app.models.schemas import AccountCreate, AccountResponse
from backend.app.repositories.db import db_manager
from backend.app.api.security import require_customer_or_admin, session_customer_id

router = APIRouter(prefix="/accounts", tags=["Accounts"])


def _scope(request: Request):
    """Row-level scope for session-authenticated customers (None = staff/service)."""
    return session_customer_id(request)


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    request: Request,
    role: str = Depends(require_customer_or_admin),
):
    scope = _scope(request)
    if scope is not None and int(payload.customer_id) != int(scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customers may only open accounts for their own customer record.",
        )

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT customer_id FROM CUSTOMER WHERE customer_id = %s;", (payload.customer_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Customer ID {payload.customer_id} does not exist.")

            try:
                cur.execute(
                    "INSERT INTO ACCOUNT (customer_id, type, balance, status, created_at) VALUES (%s, %s, %s, 'ACTIVE', NOW()) RETURNING account_id, customer_id, type, balance, status, created_at;",
                    (payload.customer_id, payload.type, payload.initial_balance)
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row)
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    request: Request,
    role: str = Depends(require_customer_or_admin),
):
    scope = _scope(request)
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id, customer_id, type, balance, status, created_at FROM ACCOUNT WHERE account_id = %s;", (account_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Account not found.")
            if scope is not None and int(row["customer_id"]) != int(scope):
                # 404 rather than 403 so account IDs cannot be enumerated.
                raise HTTPException(status_code=404, detail="Account not found.")
            return dict(row)


@router.get("", response_model=List[AccountResponse])
def list_accounts(request: Request, role: str = Depends(require_customer_or_admin)):
    scope = _scope(request)
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            if scope is not None:
                cur.execute(
                    "SELECT account_id, customer_id, type, balance, status, created_at FROM ACCOUNT WHERE customer_id = %s ORDER BY account_id ASC;",
                    (scope,),
                )
            else:
                cur.execute("SELECT account_id, customer_id, type, balance, status, created_at FROM ACCOUNT ORDER BY account_id ASC;")
            rows = cur.fetchall()
            return [dict(r) for r in rows]
