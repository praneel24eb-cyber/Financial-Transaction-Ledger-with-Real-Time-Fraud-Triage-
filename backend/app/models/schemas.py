from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field

# Customer Schemas
class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    kyc_status: str = Field(default="PENDING", pattern="^(PENDING|VERIFIED|REJECTED)$")

class CustomerResponse(BaseModel):
    customer_id: int
    name: str
    email: str
    kyc_status: str
    created_at: datetime

# Account Schemas
class AccountCreate(BaseModel):
    customer_id: int
    account_type: str = Field(..., pattern="^(SAVINGS|CURRENT|WALLET)$")
    initial_balance: float = Field(default=0.0, ge=0.0)

class AccountResponse(BaseModel):
    account_id: int
    customer_id: int
    account_type: str
    balance: float
    status: str
    created_at: datetime

# Transfer / Transaction Schemas
class TransferRequest(BaseModel):
    source_account_id: int
    destination_account_id: int
    amount: float = Field(..., gt=0.0)
    device_id: Optional[int] = None
    merchant_id: Optional[int] = None
    isolation_level: Optional[str] = Field(default="READ COMMITTED", pattern="^(READ COMMITTED|REPEATABLE READ|SERIALIZABLE)$")

class LedgerEntryResponse(BaseModel):
    entry_id: int
    txn_id: int
    account_id: int
    direction: str
    amount: float
    created_at: datetime

class FraudResultResponse(BaseModel):
    result_id: int
    txn_id: int
    risk_score: int
    model_version: str
    decision: str
    created_at: datetime

class TransferResponse(BaseModel):
    txn_id: Optional[int] = None
    status: str
    message: str
    risk_score: Optional[int] = None
    decision: Optional[str] = None
    source_balance: Optional[float] = None
    destination_balance: Optional[float] = None
    ledger_entries: List[LedgerEntryResponse] = []

# Analyst Schemas
class AnalystResponse(BaseModel):
    analyst_id: int
    name: str
    role: Optional[str] = None

# Fraud Alert & Analyst Review Schemas
class FraudAlertResponse(BaseModel):
    alert_id: int
    result_id: int
    severity: str
    status: str
    created_at: datetime
    evidence: Optional[Dict[str, Any]] = None

class AnalystReviewCreate(BaseModel):
    analyst_id: int
    decision: str = Field(..., pattern="^(CONFIRM_FRAUD|FALSE_POSITIVE|ESCALATE)$")

class AnalystReviewResponse(BaseModel):
    review_id: int
    alert_id: int
    analyst_id: int
    decision: str
    reviewed_at: datetime

# Audit Log Schema
class AuditLogResponse(BaseModel):
    audit_id: int
    table_name: str
    operation: str
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None
    prev_hash: Optional[str] = None
    row_hash: str
    created_at: datetime

