import json
import logging
from typing import List, Dict, Any, Tuple
from backend.app.repositories.db import db_manager, compute_audit_hash

logger = logging.getLogger(__name__)

class AuditService:
    @staticmethod
    def record_audit_entry(conn, table_name: str, operation: str, old_data: dict = None, new_data: dict = None):
        """
        Inserts an append-only hash-chained row into AUDIT_LOG within an existing PostgreSQL transaction.
        """
        with conn.cursor() as cur:
            cur.execute("SELECT row_hash FROM AUDIT_LOG ORDER BY audit_id DESC LIMIT 1;")
            row = cur.fetchone()
            prev_hash = row['row_hash'] if row and 'row_hash' in row else None

            prev_hash, row_hash = compute_audit_hash(prev_hash, table_name, operation, old_data, new_data)

            old_json = json.dumps(old_data) if old_data else None
            new_json = json.dumps(new_data) if new_data else None

            query = """
                INSERT INTO AUDIT_LOG (table_name, operation, old_data, new_data, prev_hash, row_hash, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW());
            """
            cur.execute(query, (table_name, operation, old_json, new_json, prev_hash, row_hash))

    @staticmethod
    def verify_hash_chain() -> Dict[str, Any]:
        """
        Scans all AUDIT_LOG rows sequentially from audit_id = 1.
        Re-calculates every SHA-256 row_hash and verifies the prev_hash link.
        Returns: { 'is_valid': bool, 'total_rows': int, 'tampered_audit_id': Optional[int], 'message': str }
        """
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT audit_id, table_name, operation, old_data, new_data, prev_hash, row_hash FROM AUDIT_LOG ORDER BY audit_id ASC;")
                rows = cur.fetchall()

                if not rows:
                    return {
                        "is_valid": True,
                        "total_rows": 0,
                        "tampered_audit_id": None,
                        "message": "Audit log is empty. Chain intact."
                    }

                expected_prev_hash = "0" * 64

                for idx, r in enumerate(rows):
                    audit_id = r['audit_id']
                    table_name = r['table_name']
                    operation = r['operation']
                    old_data_raw = r['old_data']
                    new_data_raw = r['new_data']
                    stored_prev_hash = r['prev_hash']
                    stored_row_hash = r['row_hash']

                    old_data = json.loads(old_data_raw) if isinstance(old_data_raw, str) and old_data_raw else old_data_raw
                    new_data = json.loads(new_data_raw) if isinstance(new_data_raw, str) and new_data_raw else new_data_raw

                    # Check 1: prev_hash linkage match
                    if stored_prev_hash and stored_prev_hash != expected_prev_hash:
                        return {
                            "is_valid": False,
                            "total_rows": len(rows),
                            "tampered_audit_id": audit_id,
                            "message": f"Tampering detected at audit_id {audit_id}: stored prev_hash does not match previous row's row_hash."
                        }

                    # Check 2: recompute current row_hash
                    _, recomputed_row_hash = compute_audit_hash(expected_prev_hash, table_name, operation, old_data, new_data)

                    if recomputed_row_hash != stored_row_hash:
                        return {
                            "is_valid": False,
                            "total_rows": len(rows),
                            "tampered_audit_id": audit_id,
                            "message": f"Tampering detected at audit_id {audit_id}: row content does not match stored SHA-256 row_hash."
                        }

                    expected_prev_hash = stored_row_hash

                return {
                    "is_valid": True,
                    "total_rows": len(rows),
                    "tampered_audit_id": None,
                    "message": f"Verified {len(rows)} audit rows. Hash chain is 100% valid and tamper-free."
                }

audit_service = AuditService()
