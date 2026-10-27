import time
import logging
from concurrent.futures import ThreadPoolExecutor
from backend.app.repositories.db import db_manager
from backend.app.services.ledger_service import ledger_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(threadName)s] - %(levelname)s - %(message)s")
logger = logging.getLogger("ConcurrencyDemo")

def run_concurrent_transfer_demo():
    """
    Demonstrates deterministic row-level locking (account_id ASC) preventing lost updates
    and deadlocks under concurrent transfers in opposite directions.
    """
    print("\n=======================================================================")
    print(" 🔒 POSTGRESQL CONCURRENT TRANSFER LOCKING & DEADLOCK PREVENTION DEMO ")
    print("=======================================================================\n")

    # 1. Fetch two active account IDs
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id, balance FROM ACCOUNT WHERE status = 'ACTIVE' LIMIT 2;")
            rows = cur.fetchall()
            if len(rows) < 2:
                print("Error: Need at least 2 active accounts in database to run demo.")
                return

            acc1 = rows[0]['account_id']
            acc2 = rows[1]['account_id']

            # Reset balances for demo
            cur.execute("UPDATE ACCOUNT SET balance = 10000.00 WHERE account_id IN (%s, %s);", (acc1, acc2))
            conn.commit()

    print(f"Initial State: Account #{acc1} = ₹10,000.00 | Account #{acc2} = ₹10,000.00")
    print(f"Total Initial System Balance: ₹20,000.00\n")
    print("Launching 2 concurrent threads transferring in OPPOSITE directions simultaneously...")

    def transfer_direction_1():
        logger.info(f"Thread-1 initiating transfer: Acc #{acc1} -> Acc #{acc2} (₹500.00)")
        res = ledger_service.execute_transfer(
            source_account_id=acc1,
            destination_account_id=acc2,
            amount=500.00,
            device_id=1
        )
        logger.info(f"Thread-1 completed: status={res['status']}, txn_id={res['txn_id']}")
        return res

    def transfer_direction_2():
        logger.info(f"Thread-2 initiating transfer: Acc #{acc2} -> Acc #{acc1} (₹500.00)")
        res = ledger_service.execute_transfer(
            source_account_id=acc2,
            destination_account_id=acc1,
            amount=500.00,
            device_id=2
        )
        logger.info(f"Thread-2 completed: status={res['status']}, txn_id={res['txn_id']}")
        return res

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(transfer_direction_1)
        f2 = executor.submit(transfer_direction_2)
        r1 = f1.result()
        r2 = f2.result()
    elapsed = time.time() - start_time

    # Verify final balances
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id, balance FROM ACCOUNT WHERE account_id IN (%s, %s);", (acc1, acc2))
            final_rows = cur.fetchall()
            b1 = float(final_rows[0]['balance']) if final_rows[0]['account_id'] == acc1 else float(final_rows[1]['balance'])
            b2 = float(final_rows[1]['balance']) if final_rows[1]['account_id'] == acc2 else float(final_rows[0]['balance'])
            tot = b1 + b2

    print("\n-----------------------------------------------------------------------")
    print(f"Final State: Account #{acc1} = ₹{b1:.2f} | Account #{acc2} = ₹{b2:.2f}")
    print(f"Total Final System Balance: ₹{tot:.2f}")
    print(f"Execution Time: {elapsed * 1000:.2f} ms")
    print("-----------------------------------------------------------------------")
    if tot == 20000.00:
        print("✔ DEMO SUCCESS: Zero lost updates! Lock-ordering (account_id ASC) prevented deadlocks.")
    else:
        print("❌ DEMO FAILURE: Inconsistent total balance detected.")
    print("=======================================================================\n")

if __name__ == "__main__":
    run_concurrent_transfer_demo()
