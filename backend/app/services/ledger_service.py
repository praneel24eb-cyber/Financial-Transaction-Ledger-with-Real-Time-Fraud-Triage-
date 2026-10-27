import json
import logging
from typing import Dict, Any, Tuple, Optional
from fastapi import HTTPException, status
from backend.app.repositories.db import db_manager
from backend.app.repositories.redis_repo import redis_repo
from backend.app.fraud.features import extract_fraud_features
from backend.app.fraud.infer import fraud_engine
from backend.app.services.audit_service import audit_service

logger = logging.getLogger(__name__)

class LedgerService:
    @staticmethod
    def execute_transfer(
        source_account_id: int,
        destination_account_id: int,
        amount: float,
        device_id: int,
        merchant_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes an atomic money transfer between two accounts with real-time fraud triage in PostgreSQL:
        1. Opens single PostgreSQL transaction.
        2. Acquires row-level locks FOR UPDATE in ascending lock-order (account_id ASC) to eliminate deadlocks.
        3. Validates account status and sufficient balance.
        4. Extracts features & scores via Isolation Forest (with fail-safe manual review fallback).
        5. Triage decision (<50 approve, 50-80 approve+alert, >80 rollback & flag).
        6. Inserts balanced DEBIT and CREDIT ledger entries.
        7. Records hash-chained audit log & outbox event.
        8. Commits transaction.
        """
        if source_account_id == destination_account_id:
            raise HTTPException(status_code=400, detail="Self-transfer is not permitted (source and destination accounts must differ).")

        if amount <= 0:
            raise HTTPException(status_code=400, detail="Transfer amount must be strictly greater than zero.")

        # Fixed lock ordering: sort account IDs ascending to prevent circular waits & deadlocks
        first_lock_id, second_lock_id = sorted([source_account_id, destination_account_id])

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    # 1. Acquire Row-Level Locks FOR UPDATE in ascending account_id order
                    lock_query = """
                        SELECT account_id, customer_id, balance, status 
                        FROM ACCOUNT 
                        WHERE account_id IN (%s, %s) 
                        ORDER BY account_id ASC 
                        FOR UPDATE;
                    """
                    cur.execute(lock_query, (first_lock_id, second_lock_id))

                    locked_rows = cur.fetchall()
                    accounts_by_id = {r['account_id']: r for r in locked_rows}

                    if source_account_id not in accounts_by_id:
                        raise HTTPException(status_code=404, detail=f"Source account ID {source_account_id} not found.")
                    if destination_account_id not in accounts_by_id:
                        raise HTTPException(status_code=404, detail=f"Destination account ID {destination_account_id} not found.")

                    src_acc = accounts_by_id[source_account_id]
                    dst_acc = accounts_by_id[destination_account_id]

                    src_status = src_acc['status']
                    src_balance = float(src_acc['balance'])
                    dst_status = dst_acc['status']
                    dst_balance = float(dst_acc['balance'])

                    # Check account state
                    if src_status != 'ACTIVE':
                        raise HTTPException(status_code=403, detail=f"Source account is currently {src_status} and cannot initiate transfers.")
                    if dst_status != 'ACTIVE':
                        raise HTTPException(status_code=403, detail=f"Destination account is currently {dst_status}.")

                    # Check sufficient funds
                    if src_balance < amount:
                        raise HTTPException(status_code=402, detail=f"Insufficient funds: available balance is ₹{src_balance:.2f}, required ₹{amount:.2f}.")

                    # 2. Extract Fraud Features & Score via Isolation Forest (or Fail-Safe Fallback)
                    features = extract_fraud_features(source_account_id, amount, device_id, merchant_id)
                    risk_score, decision, model_version = fraud_engine.score_transaction(features)

                    logger.info(f"Transfer request src={source_account_id} dst={destination_account_id} amt={amount} -> Risk Score={risk_score}, Decision={decision} (model: {model_version})")

                    # 3. High-Risk Triage Policy: ROLLBACK & FLAG ACCOUNT
                    if decision == "ROLLBACK":
                        cur.execute("UPDATE ACCOUNT SET status = 'FLAGGED' WHERE account_id = %s;", (source_account_id,))

                        cur.execute(
                            "INSERT INTO TRANSACTION (type, status, merchant_id, device_id, initiated_at) VALUES ('TRANSFER', 'ROLLED_BACK', %s, %s, NOW()) RETURNING txn_id;",
                            (merchant_id, device_id)
                        )
                        rb_txn_id = cur.fetchone()['txn_id']

                        cur.execute("INSERT INTO FRAUD_RESULT (txn_id, risk_score, model_version, decision, created_at) VALUES (%s, %s, %s, 'ROLLBACK', NOW());", (rb_txn_id, risk_score, model_version))
                        cur.execute("INSERT INTO FRAUD_ALERT (txn_id, severity, status, created_at) VALUES (%s, 'HIGH', 'OPEN', NOW());", (rb_txn_id,))

                        audit_service.record_audit_entry(conn, "ACCOUNT", "UPDATE", old_data={"account_id": source_account_id, "status": src_status}, new_data={"account_id": source_account_id, "status": "FLAGGED"})

                        conn.commit()

                        raise HTTPException(
                            status_code=403,
                            detail=f"Transaction DECLINED for high risk score ({risk_score}/100). Source account has been FLAGGED for security review."
                        )

                    # 4. Low/Medium Risk Flow: APPROVE / APPROVE+ALERT -> Insert TRANSACTION (COMPLETED)
                    cur.execute(
                        "INSERT INTO TRANSACTION (type, status, merchant_id, device_id, initiated_at) VALUES ('TRANSFER', 'COMPLETED', %s, %s, NOW()) RETURNING txn_id;",
                        (merchant_id, device_id)
                    )
                    txn_id = cur.fetchone()['txn_id']

                    # 5. Insert Balanced Double-Entry LEDGER_ENTRY rows (DEBIT source, CREDIT destination)
                    cur.execute("INSERT INTO LEDGER_ENTRY (txn_id, account_id, direction, amount, created_at) VALUES (%s, %s, 'DEBIT', %s, NOW());", (txn_id, source_account_id, amount))
                    cur.execute("INSERT INTO LEDGER_ENTRY (txn_id, account_id, direction, amount, created_at) VALUES (%s, %s, 'CREDIT', %s, NOW());", (txn_id, destination_account_id, amount))

                    # 6. Update Account Balances
                    new_src_balance = src_balance - amount
                    new_dst_balance = dst_balance + amount

                    cur.execute("UPDATE ACCOUNT SET balance = %s WHERE account_id = %s;", (new_src_balance, source_account_id))
                    cur.execute("UPDATE ACCOUNT SET balance = %s WHERE account_id = %s;", (new_dst_balance, destination_account_id))

                    # 7. Record Fraud Result & optional Alert if 50 <= risk_score <= 80 (or Fail-Safe Alert)
                    cur.execute("INSERT INTO FRAUD_RESULT (txn_id, risk_score, model_version, decision, created_at) VALUES (%s, %s, %s, %s, NOW());", (txn_id, risk_score, model_version, decision))

                    if decision == "ALERT":
                        cur.execute("INSERT INTO FRAUD_ALERT (txn_id, severity, status, created_at) VALUES (%s, 'MEDIUM', 'OPEN', NOW());", (txn_id,))

                    # 8. Record Hash-Chained Audit Logs for Account Mutations & Transaction Creation
                    audit_service.record_audit_entry(
                        conn, "ACCOUNT", "UPDATE",
                        old_data={"account_id": source_account_id, "balance": src_balance},
                        new_data={"account_id": source_account_id, "balance": new_src_balance}
                    )
                    audit_service.record_audit_entry(
                        conn, "ACCOUNT", "UPDATE",
                        old_data={"account_id": destination_account_id, "balance": dst_balance},
                        new_data={"account_id": destination_account_id, "balance": new_dst_balance}
                    )
                    audit_service.record_audit_entry(
                        conn, "TRANSACTION", "INSERT",
                        old_data=None,
                        new_data={"txn_id": txn_id, "status": "COMPLETED", "amount": amount}
                    )

                    # 9. Write OUTBOX_EVENT for asynchronous propagation to Redis & MongoDB
                    outbox_payload = {
                        "txn_id": txn_id,
                        "source_account_id": source_account_id,
                        "destination_account_id": destination_account_id,
                        "amount": amount,
                        "device_id": device_id,
                        "merchant_id": merchant_id,
                        "risk_score": risk_score,
                        "decision": decision,
                        "model_version": model_version,
                        "features": features
                    }
                    outbox_json = json.dumps(outbox_payload)

                    cur.execute("INSERT INTO OUTBOX_EVENT (txn_id, event_type, payload, status, created_at) VALUES (%s, 'LEDGER_POSTED', %s, 'PENDING', NOW());", (txn_id, outbox_json))

                    # 10. Atomic Commit
                    conn.commit()

                    # Sync Redis counters
                    redis_repo.add_recent_device(source_account_id, device_id)
                    redis_repo.increment_velocity(source_account_id, window_seconds=3600)

                    return {
                        "txn_id": txn_id,
                        "status": "COMPLETED",
                        "message": f"Transfer of ₹{amount:.2f} completed successfully." + (" (Flagged for Analyst Review)" if decision == "ALERT" else ""),
                        "risk_score": risk_score,
                        "decision": decision,
                        "model_version": model_version,
                        "source_balance": new_src_balance,
                        "destination_balance": new_dst_balance
                    }

                except HTTPException:
                    conn.rollback()
                    raise
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Transfer transaction failed with exception: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"Transaction processing error: {str(e)}")

ledger_service = LedgerService()
