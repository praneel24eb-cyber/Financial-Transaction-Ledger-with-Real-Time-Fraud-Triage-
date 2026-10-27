-- PostgreSQL Triggers for Financial Balance Validation and Audit Hash-Chaining

-- 1. Deferred Constraint Trigger Function for Ledger Entry Balance Validation
-- Asserts that for every committed transaction, SUM(debits) = SUM(credits)
CREATE OR REPLACE FUNCTION check_ledger_balance()
RETURNS TRIGGER AS $$
DECLARE
    v_debit_sum NUMERIC(18,2);
    v_credit_sum NUMERIC(18,2);
BEGIN
    SELECT COALESCE(SUM(amount), 0.00) INTO v_debit_sum
    FROM LEDGER_ENTRY
    WHERE txn_id = NEW.txn_id AND direction = 'DEBIT';

    SELECT COALESCE(SUM(amount), 0.00) INTO v_credit_sum
    FROM LEDGER_ENTRY
    WHERE txn_id = NEW.txn_id AND direction = 'CREDIT';

    IF v_debit_sum <> v_credit_sum THEN
        RAISE EXCEPTION 'Ledger entry imbalance for txn_id %: Total DEBIT (%) does not equal Total CREDIT (%)',
            NEW.txn_id, v_debit_sum, v_credit_sum;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Deferred constraint trigger on LEDGER_ENTRY
DROP TRIGGER IF EXISTS trigger_check_ledger_balance ON LEDGER_ENTRY;
CREATE CONSTRAINT TRIGGER trigger_check_ledger_balance
AFTER INSERT OR UPDATE ON LEDGER_ENTRY
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION check_ledger_balance();


-- 2. Audit Hash-Chaining Trigger Function
-- Computes SHA-256 of prev_hash || table_name || operation || old_data || new_data
CREATE OR REPLACE FUNCTION audit_trigger_func()
RETURNS TRIGGER AS $$
DECLARE
    v_prev_hash CHAR(64);
    v_row_hash CHAR(64);
    v_old_data JSONB := NULL;
    v_new_data JSONB := NULL;
    v_op CHAR(6);
    v_data_to_hash TEXT;
BEGIN
    v_op := TG_OP;

    IF v_op = 'UPDATE' OR v_op = 'DELETE' THEN
        v_old_data := to_jsonb(OLD);
    END IF;

    IF v_op = 'INSERT' OR v_op = 'UPDATE' THEN
        v_new_data := to_jsonb(NEW);
    END IF;

    -- Retrieve the most recent row_hash from AUDIT_LOG
    SELECT row_hash INTO v_prev_hash
    FROM AUDIT_LOG
    ORDER BY audit_id DESC
    LIMIT 1;

    IF v_prev_hash IS NULL THEN
        v_prev_hash := REPEAT('0', 64);
    END IF;

    -- Format string to hash: prev_hash | table_name | operation | old_data | new_data
    v_data_to_hash := v_prev_hash || '|' ||
                      TG_TABLE_NAME || '|' ||
                      v_op || '|' ||
                      COALESCE(v_old_data::text, '') || '|' ||
                      COALESCE(v_new_data::text, '');

    v_row_hash := encode(digest(v_data_to_hash, 'sha256'), 'hex');

    INSERT INTO AUDIT_LOG (table_name, operation, old_data, new_data, prev_hash, row_hash, created_at)
    VALUES (TG_TABLE_NAME, v_op, v_old_data, v_new_data, v_prev_hash, v_row_hash, NOW());

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Attach Audit Triggers to Audited Tables
DROP TRIGGER IF EXISTS audit_customer_trigger ON CUSTOMER;
CREATE TRIGGER audit_customer_trigger
AFTER INSERT OR UPDATE OR DELETE ON CUSTOMER
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_device_trigger ON DEVICE;
CREATE TRIGGER audit_device_trigger
AFTER INSERT OR UPDATE OR DELETE ON DEVICE
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_merchant_trigger ON MERCHANT;
CREATE TRIGGER audit_merchant_trigger
AFTER INSERT OR UPDATE OR DELETE ON MERCHANT
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_account_trigger ON ACCOUNT;
CREATE TRIGGER audit_account_trigger
AFTER INSERT OR UPDATE OR DELETE ON ACCOUNT
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_transaction_trigger ON TRANSACTION;
CREATE TRIGGER audit_transaction_trigger
AFTER INSERT OR UPDATE OR DELETE ON TRANSACTION
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_ledger_entry_trigger ON LEDGER_ENTRY;
CREATE TRIGGER audit_ledger_entry_trigger
AFTER INSERT OR UPDATE OR DELETE ON LEDGER_ENTRY
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_fraud_result_trigger ON FRAUD_RESULT;
CREATE TRIGGER audit_fraud_result_trigger
AFTER INSERT OR UPDATE OR DELETE ON FRAUD_RESULT
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_fraud_alert_trigger ON FRAUD_ALERT;
CREATE TRIGGER audit_fraud_alert_trigger
AFTER INSERT OR UPDATE OR DELETE ON FRAUD_ALERT
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_analyst_trigger ON ANALYST;
CREATE TRIGGER audit_analyst_trigger
AFTER INSERT OR UPDATE OR DELETE ON ANALYST
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_analyst_review_trigger ON ANALYST_REVIEW;
CREATE TRIGGER audit_analyst_review_trigger
AFTER INSERT OR UPDATE OR DELETE ON ANALYST_REVIEW
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

DROP TRIGGER IF EXISTS audit_outbox_trigger ON OUTBOX;
CREATE TRIGGER audit_outbox_trigger
AFTER INSERT OR UPDATE OR DELETE ON OUTBOX
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

