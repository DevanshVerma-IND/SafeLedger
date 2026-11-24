"""PostgreSQL access layer for SafeLedger.

Postgres mode is ON when the environment variable SAFELEDGER_PG_DSN is set, e.g.
    export SAFELEDGER_PG_DSN="postgresql://safeledger:pass@localhost:5432/safeledger"
When it is not set, the project behaves exactly as before (SQLite + synthetic generator), so
selftest.py and the other checks still work on a machine without a database.

SAFELEDGER_PG_SYNC_COMMIT (default "off") sets synchronous_commit for the account store. "off" is the
closest match to the old SQLite setting (WAL, synchronous=NORMAL); use "on" for full fsync per commit.
psycopg2 is imported lazily, so it is only needed when Postgres mode is on.
"""
import os, threading
from contextlib import contextmanager

SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql", "schema.sql")
POOL_MAX = 64


def dsn(): return os.environ.get("SAFELEDGER_PG_DSN")
def enabled(): return bool(dsn())


def _sync_option(): return f"-c synchronous_commit={os.environ.get('SAFELEDGER_PG_SYNC_COMMIT', 'off')}"


def connect():
    import psycopg2
    return psycopg2.connect(dsn(), options=_sync_option())


def pool():
    """Thread-safe connection pool for the live account store (one connection per busy thread)."""
    from psycopg2.pool import ThreadedConnectionPool
    return ThreadedConnectionPool(1, POOL_MAX, dsn(), options=_sync_option())


@contextmanager
def session():
    """One short transaction: commit on success, rollback on error, always close."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def init_schema():
    with session() as cur:
        cur.execute(open(SCHEMA_FILE).read())


# ------------------------------------------------------------------ workloads
def workload_seeds(split):
    """Seeds of all workloads in a split ('train', 'test', 'benchmark', 'sweep', 'selftest')."""
    with session() as cur:
        cur.execute("SELECT seed FROM workloads WHERE split = %s ORDER BY seed", (split,))
        return [r[0] for r in cur.fetchall()]


def fetch_workload(n, seed):
    """First n transfer requests of the workload with this seed.
    Returns (workload_id, split, [(tid, src, dst, amount, fee, fee_account, priority), ...])."""
    with session() as cur:
        cur.execute("SELECT workload_id, split FROM workloads WHERE seed = %s", (seed,))
        row = cur.fetchone()
        if row is None:
            raise LookupError(f"no workload with seed {seed} in Postgres; run seed_postgres.py or import your data")
        wid, split = row
        cur.execute("""SELECT tid, src_account, dst_account, amount, fee, fee_account, priority
                       FROM transfer_requests WHERE workload_id = %s ORDER BY tid LIMIT %s""", (wid, n))
        recs = cur.fetchall()
    if len(recs) < n:
        raise ValueError(f"workload seed {seed} has only {len(recs)} transfers, {n} requested")
    return wid, split, recs


# ----------------------------------------------------------------------- runs
def new_run(workload_id, purpose, mode, workers):
    with session() as cur:
        cur.execute("INSERT INTO runs(workload_id, purpose, mode, workers) VALUES (%s,%s,%s,%s) RETURNING run_id",
                    (workload_id, purpose, mode, workers))
        return cur.fetchone()[0]


RUN_COLS = ["txns", "committed", "failed", "retries", "deadlocks", "timeouts", "banker_waits",
            "ml_delays", "ml_fallbacks", "wall_s", "tps", "p50_ms", "p95_ms", "cpu_ms_per_txn", "money_conserved"]

def finish_run(run_id, res):
    sets = ", ".join(f"{c} = %({c})s" for c in RUN_COLS)
    with session() as cur:
        cur.execute(f"UPDATE runs SET finished_at = now(), {sets} WHERE run_id = %(run_id)s", {**res, "run_id": run_id})


def reset_split(purpose):
    """Delete earlier runs of one purpose (cascades to their lock_events), so re-running
    collect_train.py replaces the dataset instead of mixing old and new rows."""
    with session() as cur:
        cur.execute("DELETE FROM runs WHERE purpose = %s", (purpose,))


# ------------------------------------------------------------------ telemetry
def save_events(run_id, rows):
    from psycopg2.extras import execute_values
    data = [(run_id, r["tid"], r["attempt"], r["locks_held_on_target"], r["wait_queue_length"],
             r["account_contention_count"], r["wait_time_ms"], r["priority"], r["outcome"], r["label"]) for r in rows]
    with session() as cur:
        execute_values(cur, """INSERT INTO lock_events(run_id, tid, attempt, locks_held_on_target, wait_queue_length,
                               account_contention_count, wait_time_ms, priority, outcome, label) VALUES %s""", data, page_size=1000)


def load_events(split):
    """Training matrix straight from the database view. split = 'train' or 'test'."""
    import numpy as np
    view = {"train": "v_train_set", "test": "v_test_set"}[split]
    with session() as cur:
        cur.execute(f"""SELECT locks_held_on_target, wait_queue_length, account_contention_count, wait_time_ms,
                               priority, label FROM {view} ORDER BY event_id""")
        a = np.array(cur.fetchall(), float)
    if a.ndim != 2: raise LookupError(f"no '{split}' rows in lock_events: run collect_train.py without --from-db first")
    return a[:, :5], a[:, 5].astype(int)


def save_model(m, artifact_path):
    import json
    with session() as cur:
        cur.execute("""INSERT INTO model_registry(train_rows, test_rows, positive_share_test, precision_score, recall_score,
                       f1_score, roc_auc, false_positive_rate, predict_ms_per_call, confusion_matrix, feature_importance,
                       artifact_path) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (m["train_rows"], m["test_rows"], m["positive_share_test"], m["precision"], m["recall"], m["f1"],
                     m["roc_auc"], m["false_positive_rate"], m["predict_ms_per_call"],
                     json.dumps(m["confusion_matrix"]), json.dumps(m["feature_importance"]), artifact_path))


# ------------------------------------------------- users, roles, audit (dbms.py)
# These use their own pool with synchronous_commit=on: a login lockout or an audit entry must be durable,
# unlike the benchmark account store above, which may run with synchronous_commit=off.
_shared, _shared_lock = None, threading.Lock()

def shared_pool():
    global _shared
    with _shared_lock:
        if _shared is None:
            from psycopg2.pool import ThreadedConnectionPool
            _shared = ThreadedConnectionPool(1, 40, dsn(), options="-c synchronous_commit=on")
        return _shared

@contextmanager
def pooled_session():
    """Like session(), but borrows a connection from the shared pool (cheap enough for every request)."""
    p = shared_pool(); conn = p.getconn()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        p.putconn(conn)


def load_roles():
    """{role: {permission, ...}} from the roles / role_permissions tables."""
    with pooled_session() as cur:
        cur.execute("SELECT r.role_name, p.permission FROM roles r LEFT JOIN role_permissions p USING (role_name)")
        out = {}
        for role, perm in cur.fetchall():
            out.setdefault(role, set())
            if perm: out[role].add(perm)
    return out
