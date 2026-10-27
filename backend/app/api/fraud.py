from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends, status
from backend.app.models.schemas import AnalystReviewCreate, AnalystReviewResponse, FraudAlertResponse
from backend.app.repositories.db import db_manager
from backend.app.repositories.mongo_repo import mongo_repo
from backend.app.api.security import require_analyst_or_admin

router = APIRouter(prefix="/fraud", tags=["Fraud Triage & Alerts"])

@router.get("/alerts", response_model=List[FraudAlertResponse])
def list_fraud_alerts(status_filter: Optional[str] = Query(default=None, pattern="^(OPEN|CLOSED)$")):
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            if status_filter:
                cur.execute(
                    "SELECT alert_id, txn_id, severity, status, created_at FROM FRAUD_ALERT WHERE status = %s ORDER BY alert_id DESC;",
                    (status_filter,)
                )
            else:
                cur.execute("SELECT alert_id, txn_id, severity, status, created_at FROM FRAUD_ALERT ORDER BY alert_id DESC;")
            rows = cur.fetchall()

            alerts = []
            for r in rows:
                alert_dict = dict(r)
                txn_id = alert_dict["txn_id"]
                evidence = mongo_repo.get_fraud_evidence(txn_id)
                alert_dict["evidence"] = evidence
                alerts.append(alert_dict)

            return alerts

@router.post("/alerts/{alert_id}/review", response_model=AnalystReviewResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_analyst_or_admin)])
def submit_analyst_review(alert_id: int, payload: AnalystReviewCreate):
    """
    Records human Fraud Analyst review decision (CONFIRMED_FRAUD, FALSE_POSITIVE, ESCALATE).
    Requires 'analyst' or 'admin' role via X-User-Role header.
    """
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT alert_id, status FROM FRAUD_ALERT WHERE alert_id = %s;", (alert_id,))
            alert = cur.fetchone()

            if not alert:
                raise HTTPException(status_code=404, detail=f"Fraud alert ID {alert_id} not found.")

            if alert['status'] == 'CLOSED':
                raise HTTPException(status_code=409, detail=f"Alert ID {alert_id} has already been reviewed and closed.")

            try:
                cur.execute(
                    "INSERT INTO ANALYST_REVIEW (alert_id, analyst_id, decision, reviewed_at) VALUES (%s, %s, %s, NOW()) RETURNING review_id, alert_id, analyst_id, decision, reviewed_at;",
                    (alert_id, payload.analyst_id, payload.decision)
                )
                review_row = cur.fetchone()
                cur.execute("UPDATE FRAUD_ALERT SET status = 'CLOSED' WHERE alert_id = %s;", (alert_id,))
                conn.commit()
                return dict(review_row)
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))
