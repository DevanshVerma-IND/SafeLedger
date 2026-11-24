"""SafeLedger integrated engine: database + OS layer + admission control + ML hook.

Modes (lock strategy, optional '+ml' suffix adds the ML risk gate):
  naive    lock in business order, timeout only            (reactive baseline)
  wfg      lock in business order, Wait-For-Graph detection (database-style detector)
  ordered  lock in ascending account id (needs the lock set in advance: reference)
  banker   lock in business order, Banker's safe-state check before each grant
  X+ml     any of the above with the admission gate (GRANT / DELAY) in front
"""
import os, queue, random, shutil, sqlite3, tempfile, threading, time
from collections import defaultdict
import pg_store

FEATURES = ["locks_held_on_target", "wait_queue_length",
            "account_contention_count", "wait_time_ms", "priority"]


class Abort(Exception): pass
class LockTimeout(Abort): pass
class DeadlockVictim(Abort): pass


# ----------------------------------------------------------------- DBMS layer
class DB:
    """SQLite in WAL mode: ACID transactions, write-ahead log. Fallback used when SAFELEDGER_PG_DSN is not set."""
    def __init__(self, n_accounts=100, opening=10_000):
        self.dir = tempfile.mkdtemp(prefix="safeledger_")
        self.path = os.path.join(self.dir, "bank.db")
        self.local = threading.local()
        c = self.conn()
        c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=NORMAL")
        c.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY, balance INTEGER NOT NULL CHECK(balance>=0))")
        c.execute("CREATE TABLE txn_log(id INTEGER PRIMARY KEY AUTOINCREMENT, tid INTEGER, ts REAL, detail TEXT)")
        c.executemany("INSERT INTO accounts VALUES(?,?)", [(i, opening) for i in range(n_accounts)])
        self.initial_total = n_accounts * opening

    def conn(self):
        if not hasattr(self.local, "c"):
            self.local.c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        return self.local.c

    def apply(self, tid, legs):
        c = self.conn(); c.execute("BEGIN IMMEDIATE")
        try:
            for acct, delta in legs:
                if c.execute("UPDATE accounts SET balance=balance+? WHERE id=? AND balance+?>=0",
                             (delta, acct, delta)).rowcount != 1:
                    raise ValueError("insufficient funds")
            c.execute("INSERT INTO txn_log(tid,ts,detail) VALUES(?,?,?)", (tid, time.time(), str(legs)))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK"); raise

    def total(self):
        return self.conn().execute("SELECT SUM(balance) FROM accounts").fetchone()[0]

    def committed(self):
        return self.conn().execute("SELECT COUNT(*) FROM txn_log").fetchone()[0]

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class PgDB:
    """PostgreSQL account store (same interface as DB: apply, total, committed, close).

    Opening balances are loaded from the `accounts` table into `bank_state` under this run's id, so
    concurrent or repeated runs never touch each other's balances. Each thread borrows a pooled connection
    per transfer. The OS-layer lock manager already holds every account lock before apply() is called,
    so two apply() calls never update the same row at the same time."""
    def __init__(self, n_accounts=100, run_id=None):
        if run_id is None: raise ValueError("PgDB needs a run_id (run_load creates it)")
        self.run_id, self.pool = run_id, pg_store.pool()
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO bank_state(run_id, account_id, balance) "
                            "SELECT %s, account_id, opening_balance FROM accounts WHERE account_id < %s",
                            (run_id, n_accounts))
                if cur.rowcount != n_accounts:
                    raise ValueError(f"accounts table has {cur.rowcount} rows below id {n_accounts}, need {n_accounts}")
                cur.execute("SELECT SUM(balance) FROM bank_state WHERE run_id = %s", (run_id,))
                self.initial_total = int(cur.fetchone()[0])
            conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:
            self.pool.putconn(conn)

    def apply(self, tid, legs):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                for acct, delta in legs:
                    cur.execute("UPDATE bank_state SET balance = balance + %s "
                                "WHERE run_id = %s AND account_id = %s AND balance + %s >= 0",
                                (delta, self.run_id, acct, delta))
                    if cur.rowcount != 1: raise ValueError("insufficient funds")
                cur.execute("INSERT INTO txn_log(run_id, tid, detail) VALUES (%s, %s, %s)", (self.run_id, tid, str(legs)))
            conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:
            self.pool.putconn(conn)

    def _one(self, sql):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (self.run_id,)); v = cur.fetchone()[0]
            conn.commit(); return int(v or 0)
        finally:
            self.pool.putconn(conn)

    def total(self): return self._one("SELECT SUM(balance) FROM bank_state WHERE run_id = %s")
    def committed(self): return self._one("SELECT COUNT(*) FROM txn_log WHERE run_id = %s")

    def close(self):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur: cur.execute("DELETE FROM bank_state WHERE run_id = %s", (self.run_id,))
            conn.commit()
        finally:
            self.pool.putconn(conn); self.pool.closeall()


def make_db(n_accounts=100, run_id=None):
    """Postgres when SAFELEDGER_PG_DSN is set, otherwise the SQLite fallback."""
    return PgDB(n_accounts, run_id) if pg_store.enabled() else DB(n_accounts)


# ------------------------------------------------------------------ OS layer
class LockManager:
    """Account-level exclusive locks with wait queue, WFG detection and Banker's check."""
    def __init__(self, mode, timeout):
        self.mode, self.timeout = mode, timeout
        self.cv = threading.Condition()
        self.holder, self.held = {}, defaultdict(set)
        self.waits, self.maxset, self.prio = {}, {}, {}
        self.victims = set()
        self.stats = defaultdict(int)

    def register(self, tid, plan, prio):
        with self.cv:
            self.maxset[tid], self.prio[tid] = set(plan), prio

    def unregister(self, tid):
        with self.cv:
            for a in self.held.pop(tid, set()): self.holder.pop(a, None)
            self.waits.pop(tid, None); self.maxset.pop(tid, None); self.prio.pop(tid, None)
            self.victims.discard(tid); self.cv.notify_all()

    def _cycle(self, tid):                      # Wait-For Graph: each txn waits for one holder
        path, cur = [tid], tid
        while cur in self.waits:
            cur = self.waits[cur][1]
            if cur == tid: return path
            if cur in path or cur not in self.waits: return None
            path.append(cur)
        return None

    def _safe_after(self, tid, acct):           # Banker's Algorithm, single-instance resources
        alloc = {t: set(s) for t, s in self.held.items() if t in self.maxset}
        alloc.setdefault(tid, set()).add(acct)
        need = {t: self.maxset[t] - alloc.get(t, set()) for t in self.maxset}
        used = set().union(*alloc.values()) if alloc else set()
        avail = set().union(*self.maxset.values()) - used
        rest = set(self.maxset)
        moved = True
        while rest and moved:
            moved = False
            for t in list(rest):
                if need[t] <= avail:
                    avail |= alloc.get(t, set()); rest.discard(t); moved = True
        return not rest

    def acquire(self, tid, acct):
        deadline = time.monotonic() + self.timeout
        blocked = False
        with self.cv:
            while True:
                if tid in self.victims:
                    self.victims.discard(tid); self.waits.pop(tid, None); raise DeadlockVictim()
                h = self.holder.get(acct)
                if h is None or h == tid:
                    if self.mode == "banker" and not self._safe_after(tid, acct):
                        if not blocked: self.stats["banker_waits"] += 1; blocked = True
                    else:
                        self.holder[acct] = tid; self.held[tid].add(acct)
                        self.waits.pop(tid, None); return
                else:
                    self.waits[tid] = (acct, h)
                    if self.mode == "wfg":
                        cyc = self._cycle(tid)
                        if cyc:
                            self.stats["deadlocks"] += 1
                            victim = max(cyc, key=lambda t: (self.prio.get(t, 0), t))
                            if victim == tid:
                                self.waits.pop(tid, None); raise DeadlockVictim()
                            self.victims.add(victim); self.cv.notify_all()
                rem = deadline - time.monotonic()
                if rem <= 0:
                    if self.mode == "naive" and self._cycle(tid): self.stats["deadlocks"] += 1
                    self.waits.pop(tid, None); self.stats["timeouts"] += 1; raise LockTimeout()
                self.cv.wait(timeout=rem)

    def features(self, plan, prio, waited_ms):
        """The five ML features, measured from the live lock table."""
        with self.cv:
            plan = set(plan)
            return {
                "locks_held_on_target": sum(1 for a in plan if self.holder.get(a) is not None),
                "wait_queue_length": sum(1 for _, (a, _h) in self.waits.items() if a in plan),
                "account_contention_count": sum(1 for s in self.maxset.values() if s & plan),
                "wait_time_ms": waited_ms, "priority": prio}


# ------------------------------------------------------------- ML + admission
class Predictor:
    """In-process Random Forest. The trained forest is flattened into plain lists so one
    prediction costs tens of microseconds (sklearn's predict_proba costs about 4 ms per call)."""
    def __init__(self, path):
        import joblib; self.model = joblib.load(path); self.trees = []
        for est in self.model.estimators_:
            t = est.tree_; v = t.value[:, 0, :]; p1 = (v[:, 1] / v.sum(axis=1)).tolist()
            self.trees.append((t.children_left.tolist(), t.children_right.tolist(),
                               t.feature.tolist(), t.threshold.tolist(), p1))
    def __call__(self, f):
        x = [f[k] for k in FEATURES]; tot = 0.0
        for left, right, feat, thr, p1 in self.trees:
            n = 0
            while left[n] != -1:
                n = left[n] if x[feat[n]] <= thr[n] else right[n]
            tot += p1[n]
        return tot / len(self.trees)

class HttpPredictor:
    def __init__(self, url="http://localhost:5000/predict", timeout=0.05):
        self.url, self.timeout = url, timeout
    def __call__(self, f):
        import json, urllib.request
        try:
            req = urllib.request.Request(self.url, json.dumps(f).encode(), {"Content-Type": "application/json"})
            return float(json.loads(urllib.request.urlopen(req, timeout=self.timeout).read())["risk_score"])
        except Exception:
            return None                          # fail-safe: caller falls back to rule-based path

class Admission:
    """GRANT when risk is low, DELAY (with aging) when risk >= threshold."""
    def __init__(self, lm, predictor, threshold=0.5, backoff=0.004, max_rounds=12):
        self.lm, self.pred, self.th, self.backoff, self.max_rounds = lm, predictor, threshold, backoff, max_rounds
    def admit(self, plan, prio, t_submit):
        rounds = 0
        while True:
            f = self.lm.features(plan, prio, (time.monotonic() - t_submit) * 1000)
            risk = self.pred(f) if self.pred else None
            if risk is None or risk < self.th or rounds >= self.max_rounds:
                if risk is None and self.pred: self.lm.stats["ml_fallbacks"] += 1
                return f, risk
            rounds += 1; self.lm.stats["ml_delays"] += 1
            time.sleep(self.backoff * rounds)    # aging: delay grows, then force-admit


# ------------------------------------------------------------- transactions
class Specs(list):
    """A list of transfer dicts that remembers which Postgres workload it came from (None if synthetic)."""
    workload_id = None
    split = None


def _legs(src, dst, amt, fee, fee_acct):
    if fee_acct is None: return [(src, -amt), (dst, amt)]
    return [(src, -(amt + fee)), (dst, amt), (fee_acct, fee)]


def make_specs(n, seed, n_accounts=100, hot_set=8, hot_frac=0.7, fee_frac=0.3, source="auto"):
    """The transfer requests that become client threads.
    source="postgres": read the first n rows of the workload whose seed is `seed` from the database.
    source="synthetic": the original random generator (hot_set / hot_frac / fee_frac apply only here).
    source="auto" (default): Postgres when SAFELEDGER_PG_DSN is set, otherwise synthetic."""
    if source == "auto": source = "postgres" if pg_store.enabled() else "synthetic"
    if source == "postgres":
        wid, split, recs = pg_store.fetch_workload(n, seed)
        specs = Specs(); specs.workload_id, specs.split = wid, split
        for tid, src, dst, amt, fee, fee_acct, prio in recs:
            specs.append({"tid": tid, "legs": _legs(src, dst, amt, fee, fee_acct), "prio": prio})
        return specs
    return synthetic_specs(n, seed, n_accounts, hot_set, hot_frac, fee_frac)


def synthetic_specs(n, seed, n_accounts=100, hot_set=8, hot_frac=0.7, fee_frac=0.3):
    rng = random.Random(seed); specs = []
    fee_accts = list(range(n_accounts - 4, n_accounts))
    for tid in range(n):
        pool = range(hot_set) if rng.random() < hot_frac else range(hot_set, n_accounts - 4)
        src, dst = rng.sample(list(pool), 2); amt = rng.randint(1, 50)
        if rng.random() < fee_frac:
            fee = rng.randint(1, 3); fa = rng.choice(fee_accts)
            legs = [(src, -(amt + fee)), (dst, amt), (fa, fee)]
        else:
            legs = [(src, -amt), (dst, amt)]
        specs.append({"tid": tid, "legs": legs, "prio": rng.randint(1, 3)})
    return specs

def run_load(specs, mode, workers=16, think=0.003, predictor=None, threshold=0.5,
             naive_timeout=0.10, collect=None, max_retry=8, n_accounts=100, seed=0):
    use_ml = mode.endswith("+ml"); base = mode.replace("+ml", "")
    if use_ml and predictor is None: raise ValueError("predictor required for +ml modes")
    run_id = None
    if pg_store.enabled():
        run_id = pg_store.new_run(getattr(specs, "workload_id", None), getattr(specs, "split", None) or "adhoc",
                                  mode, workers)
    db = make_db(n_accounts, run_id); lm = LockManager(base, naive_timeout if base == "naive" else 2.0)
    adm = Admission(lm, predictor if use_ml else None, threshold)
    q = queue.Queue(); [q.put(s) for s in specs]
    lat, failed, retries, rejected = [], [0], [0], [0]; mu = threading.Lock()
    rng = random.Random(seed)

    def worker():
        while True:
            try: s = q.get_nowait()
            except queue.Empty: return
            tid, legs, prio = s["tid"], s["legs"], s["prio"]
            plan = [a for a, _ in legs]; order = sorted(plan) if base == "ordered" else plan
            t0 = time.monotonic(); done = False
            for attempt in range(max_retry):
                f, risk = adm.admit(plan, prio, t0)
                lm.register(tid, plan, prio); label, outcome = 0, "COMMIT"
                try:
                    for a in order:
                        lm.acquire(tid, a); time.sleep(think)
                    db.apply(tid, legs); done = True
                except LockTimeout:
                    label, outcome = 1, "TIMEOUT"
                except DeadlockVictim:
                    label, outcome = 1, "DEADLOCK_VICTIM"
                except ValueError:
                    outcome = "REJECTED"
                    with mu: rejected[0] += 1
                    done = True
                finally:
                    lm.unregister(tid)
                if collect is not None:
                    with mu: collect.append({**f, "label": label, "tid": tid, "attempt": attempt, "outcome": outcome})
                if done: break
                with mu: retries[0] += 1
                time.sleep(rng.uniform(0, 0.01) * (attempt + 1))
            with mu:
                if done: lat.append((time.monotonic() - t0) * 1000)
                else: failed[0] += 1

    cpu0, w0 = time.process_time(), time.monotonic()
    ts = [threading.Thread(target=worker) for _ in range(workers)]
    [t.start() for t in ts]; [t.join() for t in ts]
    wall, cpu = time.monotonic() - w0, time.process_time() - cpu0
    lat.sort(); n = max(len(lat), 1)
    pct = lambda p: lat[min(int(p * n), n - 1)] if lat else 0.0
    res = {"mode": mode, "txns": len(specs), "committed": db.committed(), "failed": failed[0],
           "retries": retries[0], "deadlocks": lm.stats["deadlocks"], "timeouts": lm.stats["timeouts"],
           "banker_waits": lm.stats["banker_waits"], "ml_delays": lm.stats["ml_delays"],
           "ml_fallbacks": lm.stats["ml_fallbacks"], "wall_s": round(wall, 3),
           "tps": round(db.committed() / wall, 1), "p50_ms": round(pct(.5), 1), "p95_ms": round(pct(.95), 1),
           "cpu_ms_per_txn": round(1000 * cpu / max(db.committed(), 1), 2),
           "money_conserved": db.total() == db.initial_total}
    if run_id is not None:
        res["run_id"] = run_id; pg_store.finish_run(run_id, res)
    db.close(); return res


def deadlock_scenario(mode, predictor=None, threshold=0.5):
    """Two opposite transfers (A->B and B->A) that deadlock under naive locking."""
    specs = [{"tid": 0, "legs": [(0, -10), (1, 10)], "prio": 1},
             {"tid": 1, "legs": [(1, -10), (0, 10)], "prio": 2}]
    return run_load(specs, mode, workers=2, think=0.05, predictor=predictor, threshold=threshold,
                    naive_timeout=0.4, n_accounts=10)
