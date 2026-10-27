from typing import List
from fastapi import APIRouter, HTTPException, status
from backend.app.models.schemas import AccountCreate, AccountResponse
from backend.app.repositories.db import db_manager

router = APIRouter(prefix="/accounts", tags=["Accounts"])

@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate):
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT customer_id FROM CUSTOMER WHERE customer_id = %s;", (payload.customer_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Customer ID {payload.customer_id} does not exist.")

            try:
                cur.execute(
                    "INSERT INTO ACCOUNT (customer_id, account_type, balance, status, created_at) VALUES (%s, %s, %s, 'ACTIVE', NOW()) RETURNING account_id, customer_id, account_type, balance, status, created_at;",
                    (payload.customer_id, payload.account_type, payload.initial_balance)
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row)
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))

@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int):
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id, customer_id, account_type, balance, status, created_at FROM ACCOUNT WHERE account_id = %s;", (account_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Account not found.")
            return dict(row)

@router.get("", response_model=List[AccountResponse])
def list_accounts():
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id, customer_id, account_type, balance, status, created_at FROM ACCOUNT ORDER BY account_id ASC;")
            rows = cur.fetchall()
            return [dict(r) for r in rows]

