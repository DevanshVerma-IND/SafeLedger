"""Create the SafeLedger tables in PostgreSQL and load the dataset.

    export SAFELEDGER_PG_DSN="postgresql://safeledger:pass@localhost:5432/safeledger"
    python seed_postgres.py                      # schema + 100 accounts + default workloads (train/test/benchmark/sweep/selftest)
    python seed_postgres.py --reset              # same, but wipes the SafeLedger tables first
    python seed_postgres.py --csv my.csv --name train-real-1 --seed 301 --split train
                                                 # import your own transfer data as one more workload

CSV columns (header required): tid,src_account,dst_account,amount,fee,fee_account,priority
(fee_account may be empty when fee is 0). Every account id used must already exist in `accounts`.

The default workloads are produced once, here, by the original generator (engine.synthetic_specs) and stored
as rows. After that the project only ever reads them from Postgres, so every run replays identical data."""
import argparse, sys
import pg_store
from engine import synthetic_specs
from dbms import ROLES

N_ACCOUNTS, OPENING, N_TXNS = 100, 10_000, 300
DEFAULT_WORKLOADS = ([(f"train-{s}", s, "train") for s in range(101, 107)] +
                     [("test-201", 201, "test")] +
                     [(f"benchmark-{s}", s, "benchmark") for s in range(1, 6)] +
                     [(f"sweep-{s}", s, "sweep") for s in range(11, 14)] +
                     [("selftest-99", 99, "selftest")])


def account_rows():
    for i in range(N_ACCOUNTS):
        if i < 8:                  kind, name = "merchant", f"Merchant {i:02d}"
        elif i >= N_ACCOUNTS - 4:  kind, name = "fee", f"Fee pool {i}"
        else:                      kind, name = "customer", f"Customer {i:03d}"
        yield i, name, kind, OPENING


def request_rows(wid, specs):
    for s in specs:
        legs = s["legs"]
        src, dst, amt = legs[0][0], legs[1][0], legs[1][1]
        fee, fee_acct = (legs[2][1], legs[2][0]) if len(legs) == 3 else (0, None)
        yield wid, s["tid"], src, dst, amt, fee, fee_acct, s["prio"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete all SafeLedger tables first")
    ap.add_argument("--csv"); ap.add_argument("--name"); ap.add_argument("--seed", type=int); ap.add_argument("--split")
    a = ap.parse_args()
    if not pg_store.enabled(): sys.exit("Set SAFELEDGER_PG_DSN first (see the top of this file).")
    from psycopg2.extras import execute_values

    if a.reset:
        with pg_store.session() as cur:
            cur.execute("DROP VIEW IF EXISTS v_train_set, v_test_set; DROP TABLE IF EXISTS model_registry, lock_events, "
                        "txn_log, bank_state, runs, transfer_requests, workloads, user_accounts, app_users, role_permissions, roles, "
                        "audit_log, accounts CASCADE")
    pg_store.init_schema()

    if a.csv:
        if not (a.name and a.seed is not None and a.split): sys.exit("--csv needs --name, --seed and --split")
        with pg_store.session() as cur:
            cur.execute("INSERT INTO workloads(name, seed, split, description) VALUES (%s,%s,%s,%s) RETURNING workload_id",
                        (a.name, a.seed, a.split, f"imported from {a.csv}"))
            wid = cur.fetchone()[0]
            cur.execute("""CREATE TEMP TABLE stg(tid INT, src_account INT, dst_account INT, amount INT, fee INT,
                           fee_account INT, priority SMALLINT) ON COMMIT DROP""")
            with open(a.csv) as f:
                cur.copy_expert("COPY stg FROM STDIN WITH (FORMAT csv, HEADER true)", f)
            cur.execute("""INSERT INTO transfer_requests SELECT %s, tid, src_account, dst_account, amount, COALESCE(fee,0),
                           fee_account, priority FROM stg""", (wid,))
            print(f"imported {cur.rowcount} transfers as workload '{a.name}' (seed {a.seed}, split {a.split})")
        return

    with pg_store.session() as cur:
        cur.execute("SELECT COUNT(*) FROM accounts"); have = cur.fetchone()[0]
        if have == 0:
            execute_values(cur, "INSERT INTO accounts(account_id, holder_name, account_type, opening_balance) VALUES %s",
                           list(account_rows()))
        for role, perms in ROLES.items():                  # roles and permissions: defaults from dbms.ROLES, then owned by the DB
            cur.execute("INSERT INTO roles(role_name) VALUES (%s) ON CONFLICT DO NOTHING", (role,))
            for p in perms:
                cur.execute("INSERT INTO role_permissions(role_name, permission) VALUES (%s,%s) ON CONFLICT DO NOTHING", (role, p))
        for name, seed, split in DEFAULT_WORKLOADS:
            cur.execute("""INSERT INTO workloads(name, seed, split, description) VALUES (%s,%s,%s,%s)
                           ON CONFLICT (seed) DO NOTHING RETURNING workload_id""",
                        (name, seed, split, f"{N_TXNS} transfers, 70% via 8 merchant accounts, 30% with a fee leg"))
            row = cur.fetchone()
            if row is None: continue                      # already loaded earlier
            execute_values(cur, """INSERT INTO transfer_requests(workload_id, tid, src_account, dst_account, amount, fee,
                                   fee_account, priority) VALUES %s""",
                           list(request_rows(row[0], synthetic_specs(N_TXNS, seed))))
        cur.execute("SELECT split, COUNT(*) FROM workloads GROUP BY split ORDER BY split")
        for split, k in cur.fetchall(): print(f"{split:10s} {k} workload(s)")
        cur.execute("SELECT COUNT(*) FROM transfer_requests"); print("transfer_requests rows:", cur.fetchone()[0])


if __name__ == "__main__":
    main()
