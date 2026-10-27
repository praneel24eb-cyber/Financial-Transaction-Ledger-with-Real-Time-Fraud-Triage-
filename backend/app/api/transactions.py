from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from backend.app.models.schemas import TransferRequest, TransferResponse
from backend.app.services.ledger_service import ledger_service
from backend.app.repositories.db import db_manager

router = APIRouter(prefix="/transactions", tags=["Transactions"])

@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
def initiate_transfer(payload: TransferRequest):
    res = ledger_service.execute_transfer(
        source_account_id=payload.source_account_id,
        destination_account_id=payload.destination_account_id,
        amount=payload.amount,
        device_id=payload.device_id,
        merchant_id=payload.merchant_id
    )
    return res

@router.get("/{txn_id}")
def get_transaction_detail(txn_id: int):
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT txn_id, type, status, merchant_id, device_id, initiated_at FROM TRANSACTION WHERE txn_id = %s;", (txn_id,))
            txn = cur.fetchone()
            if not txn:
                raise HTTPException(status_code=404, detail="Transaction not found.")

            cur.execute("SELECT entry_id, txn_id, account_id, direction, amount, created_at FROM LEDGER_ENTRY WHERE txn_id = %s ORDER BY entry_id ASC;", (txn_id,))
            entries = cur.fetchall()

            cur.execute("SELECT risk_score, model_version, decision, created_at FROM FRAUD_RESULT WHERE txn_id = %s;", (txn_id,))
            fraud = cur.fetchone()

            return {
                "transaction": dict(txn),
                "ledger_entries": [dict(e) for e in entries],
                "fraud_result": dict(fraud) if fraud else None
            }

@router.get("/account/{account_id}")
def get_account_transaction_history(
    account_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT l.entry_id, l.txn_id, l.account_id, l.direction, l.amount, l.created_at, t.status
                FROM LEDGER_ENTRY l
                JOIN TRANSACTION t ON l.txn_id = t.txn_id
                WHERE l.account_id = %s
                ORDER BY l.entry_id DESC
                LIMIT %s OFFSET %s;
            """
            cur.execute(query, (account_id, limit, offset))
            rows = cur.fetchall()
            return [dict(r) for r in rows]
