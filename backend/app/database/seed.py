import random
import logging
from faker import Faker
from backend.app.repositories.db import db_manager
from backend.app.fraud.train import train_isolation_forest_model
from backend.app.workers.outbox_worker import outbox_worker

logger = logging.getLogger(__name__)
fake = Faker()

def seed_database(num_customers: int = 10, num_accounts: int = 15):
    """
    Seeds initial synthetic data in PostgreSQL:
    1. Schema DDL & triggers initialization.
    2. Synthetic Customers, Accounts, Devices, Merchants via Faker.
    3. Historical Transactions & Ledger Entries (~95% normal + ~5% injected anomalous patterns).
    4. IsolationForest model training fitted on generated records.
    """
    logger.info("Initializing PostgreSQL schema and seeding initial records...")
    db_manager.init_db()

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            # Clear existing records cleanly
            tables = [
                "ANALYST_REVIEW", "FRAUD_ALERT", "FRAUD_RESULT",
                "OUTBOX_EVENT", "LEDGER_ENTRY", "TRANSACTION",
                "DEVICE", "ACCOUNT", "CUSTOMER", "MERCHANT", "AUDIT_LOG"
            ]
            for tbl in tables:
                try:
                    cur.execute(f"TRUNCATE TABLE {tbl} CASCADE;")
                except Exception:
                    cur.execute(f"DELETE FROM {tbl};")
            conn.commit()

            # 1. Seed Customers
            customers = []
            for _ in range(num_customers):
                name = fake.name()
                email = fake.unique.email()
                kyc = random.choice(["VERIFIED", "VERIFIED", "VERIFIED", "PENDING"])
                cur.execute(
                    "INSERT INTO CUSTOMER (name, email, kyc_status, created_at) VALUES (%s, %s, %s, NOW()) RETURNING customer_id;",
                    (name, email, kyc)
                )
                cid = cur.fetchone()['customer_id']
                customers.append(cid)

            # 2. Seed Accounts
            accounts = []
            for i in range(num_accounts):
                cid = random.choice(customers)
                acc_type = random.choice(["SAVINGS", "CURRENT", "WALLET"])
                balance = round(random.uniform(10000.0, 100000.0), 2)
                cur.execute(
                    "INSERT INTO ACCOUNT (customer_id, type, balance, status, created_at) VALUES (%s, %s, %s, 'ACTIVE', NOW()) RETURNING account_id;",
                    (cid, acc_type, balance)
                )
                aid = cur.fetchone()['account_id']
                accounts.append(aid)

            # 3. Seed Devices
            devices = []
            for cid in customers:
                fp = fake.sha256()
                cur.execute(
                    "INSERT INTO DEVICE (customer_id, fingerprint, created_at) VALUES (%s, %s, NOW()) RETURNING device_id;",
                    (cid, fp)
                )
                did = cur.fetchone()['device_id']
                devices.append(did)

            # 4. Seed Merchants (Domestic and Foreign)
            merchants = []
            merchant_configs = [
                ("Retail", "IN"), ("Electronics", "IN"), ("Groceries", "IN"),
                ("Utilities", "IN"), ("Foreign Retail", "US"), ("Foreign Travel", "UK")
            ]
            for cat, ctry in merchant_configs:
                cur.execute(
                    "INSERT INTO MERCHANT (category, country, created_at) VALUES (%s, %s, NOW()) RETURNING merchant_id;",
                    (cat, ctry)
                )
                mid = cur.fetchone()['merchant_id']
                merchants.append(mid)

            conn.commit()

            # 5. Seed Historical Transfers (~95% normal, ~5% injected anomalous)
            num_txns = 40
            for i in range(num_txns):
                src, dst = random.sample(accounts, 2)
                dev = random.choice(devices)
                mer = random.choice(merchants)

                # Inject ~5% anomalous patterns
                is_anomaly = (i % 20 == 0)
                if is_anomaly:
                    amt = round(random.uniform(45000.0, 90000.0), 2)
                    risk_score = random.randint(81, 95)
                    decision = "ROLLBACK"
                    status = "ROLLED_BACK"
                else:
                    amt = round(random.uniform(100.0, 3000.0), 2)
                    risk_score = random.randint(5, 35)
                    decision = "APPROVE"
                    status = "COMPLETED"

                cur.execute(
                    "INSERT INTO TRANSACTION (type, status, merchant_id, device_id, initiated_at) VALUES ('TRANSFER', %s, %s, %s, NOW()) RETURNING txn_id;",
                    (status, mer, dev)
                )
                txid = cur.fetchone()['txn_id']

                if status == "COMPLETED":
                    cur.execute("INSERT INTO LEDGER_ENTRY (txn_id, account_id, direction, amount, created_at) VALUES (%s, %s, 'DEBIT', %s, NOW());", (txid, src, amt))
                    cur.execute("INSERT INTO LEDGER_ENTRY (txn_id, account_id, direction, amount, created_at) VALUES (%s, %s, 'CREDIT', %s, NOW());", (txid, dst, amt))

                cur.execute(
                    "INSERT INTO FRAUD_RESULT (txn_id, risk_score, model_version, decision, created_at) VALUES (%s, %s, 'if-v1.0', %s, NOW());",
                    (txid, risk_score, decision)
                )

            conn.commit()

    # 6. Fit IsolationForest Model on the Seeded Dataset
    logger.info("Fitting IsolationForest model on seeded records...")
    train_isolation_forest_model()

    # 7. Process pending outbox events
    outbox_worker.process_pending_events()

    logger.info("Database seeding & ML model training pipeline completed successfully.")

if __name__ == "__main__":
    seed_database()
