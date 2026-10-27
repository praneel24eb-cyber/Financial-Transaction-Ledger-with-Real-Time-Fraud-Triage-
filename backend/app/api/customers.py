from fastapi import APIRouter, HTTPException, status
from backend.app.models.schemas import CustomerCreate, CustomerResponse
from backend.app.repositories.db import db_manager

router = APIRouter(prefix="/customers", tags=["Customers"])

@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate):
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO CUSTOMER (name, email, kyc_status, created_at) VALUES (%s, %s, %s, NOW()) RETURNING customer_id, name, email, kyc_status, created_at;",
                    (payload.name, payload.email, payload.kyc_status)
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row)
            except Exception as e:
                conn.rollback()
                if "UNIQUE" in str(e).upper() or "DUPLICATE" in str(e).upper():
                    raise HTTPException(status_code=409, detail="A customer with this email address already exists.")
                raise HTTPException(status_code=400, detail=str(e))

@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int):
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT customer_id, name, email, kyc_status, created_at FROM CUSTOMER WHERE customer_id = %s;", (customer_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Customer not found.")
            return dict(row)
