from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from backend.app.models.schemas import AuditLogResponse
from backend.app.services.audit_service import audit_service
from backend.app.repositories.db import db_manager
from backend.app.api.security import require_admin

router = APIRouter(prefix="/audit", tags=["Audit Log & Verification"])

@router.get("/verify/chain", dependencies=[Depends(require_admin)])
def verify_audit_hash_chain():
    """
    Recalculates SHA-256 hashes across all AUDIT_LOG rows from audit_id = 1.
    Requires 'admin' role via X-User-Role header.
    """
    res = audit_service.verify_hash_chain()
    return res

@router.get("/{table_name}", dependencies=[Depends(require_admin)])
def get_audit_trail_for_table(
    table_name: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0)
):
    """
    Retrieves audit trail for financial tables (ACCOUNT, TRANSACTION, LEDGER_ENTRY).
    Requires 'admin' role via X-User-Role header.
    """
    table_upper = table_name.upper()

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            if table_upper == "ALL":
                cur.execute(
                    "SELECT audit_id, table_name, operation, old_data, new_data, prev_hash, row_hash, created_at FROM AUDIT_LOG ORDER BY audit_id DESC LIMIT %s OFFSET %s;",
                    (limit, offset)
                )
            else:
                cur.execute(
                    "SELECT audit_id, table_name, operation, old_data, new_data, prev_hash, row_hash, created_at FROM AUDIT_LOG WHERE table_name = %s ORDER BY audit_id DESC LIMIT %s OFFSET %s;",
                    (table_upper, limit, offset)
                )

            rows = cur.fetchall()
            return [dict(r) for r in rows]
