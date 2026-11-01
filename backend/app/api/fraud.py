from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends, status
from backend.app.models.schemas import AnalystReviewCreate, AnalystReviewResponse, FraudAlertResponse, AnalystResponse
from backend.app.repositories.db import db_manager
from backend.app.repositories.mongo_repo import mongo_repo
from backend.app.api.security import require_analyst_or_admin

router = APIRouter(prefix="/fraud", tags=["Fraud Triage & Alerts"])

@router.get("/alerts", response_model=List[FraudAlertResponse])
def list_fraud_alerts(status_filter: Optional[str] = Query(default=None, pattern="^(OPEN|REVIEWED|DISMISSED)$")):
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            if status_filter:
                cur.execute(
                    "SELECT alert_id, result_id, severity, status, created_at FROM FRAUD_ALERT WHERE status = %s ORDER BY alert_id DESC;",
                    (status_filter,)
                )
            else:
                cur.execute("SELECT alert_id, result_id, severity, status, created_at FROM FRAUD_ALERT ORDER BY alert_id DESC;")
            rows = cur.fetchall()

            alerts = []
            for r in rows:
                alert_dict = dict(r)
                alert_id = alert_dict["alert_id"]
                evidence = mongo_repo.get_alert_evidence(alert_id)
                alert_dict["evidence"] = evidence
                alerts.append(alert_dict)

            return alerts

@router.get("/analysts", response_model=List[AnalystResponse])
def list_analysts():
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT analyst_id, name, role FROM ANALYST ORDER BY analyst_id ASC;")
            rows = cur.fetchall()
            return [dict(r) for r in rows]

@router.post("/alerts/{alert_id}/review", response_model=AnalystReviewResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_analyst_or_admin)])
def submit_analyst_review(alert_id: int, payload: AnalystReviewCreate):
    """
    Records human Fraud Analyst review decision (CONFIRM_FRAUD, FALSE_POSITIVE, ESCALATE).
    Requires 'analyst' or 'admin' role via X-User-Role header.
    """
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT alert_id, status FROM FRAUD_ALERT WHERE alert_id = %s;", (alert_id,))
            alert = cur.fetchone()

            if not alert:
                raise HTTPException(status_code=404, detail=f"Fraud alert ID {alert_id} not found.")

            if alert['status'] == 'REVIEWED':
                raise HTTPException(status_code=409, detail=f"Alert ID {alert_id} has already been reviewed.")

            # Validate analyst exists
            cur.execute("SELECT analyst_id FROM ANALYST WHERE analyst_id = %s;", (payload.analyst_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Analyst ID {payload.analyst_id} not found.")

            try:
                cur.execute(
                    "INSERT INTO ANALYST_REVIEW (alert_id, analyst_id, decision, reviewed_at) VALUES (%s, %s, %s, NOW()) RETURNING review_id, alert_id, analyst_id, decision, reviewed_at;",
                    (alert_id, payload.analyst_id, payload.decision)
                )
                review_row = cur.fetchone()
                cur.execute("UPDATE FRAUD_ALERT SET status = 'REVIEWED' WHERE alert_id = %s;", (alert_id,))
                conn.commit()
                return dict(review_row)
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))

