from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends, Request, status
from backend.app.models.schemas import TransferRequest, TransferResponse
from backend.app.services.ledger_service import ledger_service
from backend.app.repositories.db import db_manager
from backend.app.api.security import require_customer_or_admin, session_customer_id

router = APIRouter(prefix="/transactions", tags=["Transactions"])

# Customer-facing wording for a rolled-back (high-risk) transfer. The numeric risk score
# and triage decision stay internal.
CUSTOMER_DECLINED_MESSAGE = (
    "This transfer was declined by automated security checks. No funds were moved "
    "and the account has been referred to our fraud team for review."
)


def _account_owner(cur, account_id: int) -> Optional[int]:
    cur.execute("SELECT customer_id FROM ACCOUNT WHERE account_id = %s;", (account_id,))
    row = cur.fetchone()
    return int(row["customer_id"]) if row else None


@router.post(
    "",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_none=True,
)
def initiate_transfer(
    payload: TransferRequest,
    request: Request,
    role: str = Depends(require_customer_or_admin),
):
    scope = session_customer_id(request)
    if scope is not None:
        # Row-level authorization: a signed-in customer may only debit their own account.
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                owner = _account_owner(cur, payload.source_account_id)
        if owner is None:
            raise HTTPException(status_code=404, detail="Source account not found.")
        if owner != int(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only transfer funds from your own accounts.",
            )

    try:
        res = ledger_service.execute_transfer(
            source_account_id=payload.source_account_id,
            destination_account_id=payload.destination_account_id,
            amount=payload.amount,
            device_id=payload.device_id,
            merchant_id=payload.merchant_id
        )
    except HTTPException as exc:
        # Never leak the ML risk score / triage reasoning to a customer.
        if role == "customer" and exc.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CUSTOMER_DECLINED_MESSAGE)
        raise

    if role == "customer":
        # Role-based data minimisation: customers receive the outcome, not the model output.
        res.pop("risk_score", None)
        res.pop("decision", None)
        res.pop("model_version", None)
        res["message"] = f"Transfer of ₹{float(payload.amount):,.2f} completed successfully."

    return res


@router.get("/{txn_id}")
def get_transaction_detail(
    txn_id: int,
    request: Request,
    role: str = Depends(require_customer_or_admin),
):
    scope = session_customer_id(request)
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT txn_id, type, status, merchant_id, device_id, initiated_at FROM TRANSACTION WHERE txn_id = %s;", (txn_id,))
            txn = cur.fetchone()
            if not txn:
                raise HTTPException(status_code=404, detail="Transaction not found.")

            if scope is not None:
                cur.execute(
                    """
                    SELECT 1 FROM LEDGER_ENTRY l
                    JOIN ACCOUNT a ON a.account_id = l.account_id
                    WHERE l.txn_id = %s AND a.customer_id = %s LIMIT 1;
                    """,
                    (txn_id, scope),
                )
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Transaction not found.")

            cur.execute("SELECT entry_id, txn_id, account_id, direction, amount, created_at FROM LEDGER_ENTRY WHERE txn_id = %s ORDER BY entry_id ASC;", (txn_id,))
            entries = cur.fetchall()

            cur.execute("SELECT risk_score, model_version, decision, created_at FROM FRAUD_RESULT WHERE txn_id = %s;", (txn_id,))
            fraud = cur.fetchone()

            return {
                "transaction": dict(txn),
                "ledger_entries": [dict(e) for e in entries],
                # ML reasoning is only exposed to staff roles.
                "fraud_result": (dict(fraud) if fraud else None) if role != "customer" else None
            }


@router.get("/account/{account_id}")
def get_account_transaction_history(
    account_id: int,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    role: str = Depends(require_customer_or_admin)
):
    scope = session_customer_id(request)
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            if scope is not None:
                owner = _account_owner(cur, account_id)
                if owner is None or owner != int(scope):
                    raise HTTPException(status_code=404, detail="Account not found.")

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
