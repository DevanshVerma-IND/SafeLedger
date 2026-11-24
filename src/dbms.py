"""SafeLedger DBMS layer: recovery (WAL, checkpoint, redo/undo, backup, point-in-time restore)
and security (authentication, roles, ownership, limits, idempotency, tamper-evident audit log).
Standard library only (psycopg2 is needed just for PostgreSQL mode: users, roles and the audit log then live in
Postgres tables instead of memory and a file). Bank at the bottom connects it to the OS layer in engine.py."""
import base64, hashlib, hmac, itertools, json, os, secrets, shutil, threading, time, zlib
from engine import Abort, Admission, LockManager
import pg_store


class StoreDown(Exception): pass
class AuthError(Exception): pass
class Forbidden(Exception): pass
class Invalid(Exception): pass


def _dump(path, obj):                       # atomic write: temp file, fsync, rename
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def _load(path):
    d = json.load(open(path)); d["balances"] = {int(k): v for k, v in d["balances"].items()}; return d

def _sha(path): return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ===================================================================== RECOVERY
class WalStore:
    """Account balances held in memory; durability comes from a write-ahead log.
    Log record = CRC32 + JSON (BEGIN, UPD with before/after image, COMMIT, ABORT).
    The log is forced to disk BEFORE the balances change (write-ahead rule)."""
    def __init__(self, path, n_accounts=100, opening=10_000, sync=True, fresh=True):
        self.path, self.sync, self.mu, self.up = path, sync, threading.Lock(), True
        os.makedirs(path, exist_ok=True)
        self.wal, self.snap, self.base = (os.path.join(path, n) for n in ("wal.log", "checkpoint.json", "base.json"))
        if fresh:
            self.balances = {i: opening for i in range(n_accounts)}; self.lsn = 0; self.committed = 0
            open(self.wal, "w").close(); _dump(self.base, {"lsn": 0, "balances": self.balances})
            _dump(self.snap, {"lsn": 0, "balances": self.balances})
        else:
            self.recover()
        self.initial_total = sum(_load(self.base)["balances"].values())

    def _next(self): self.lsn += 1; return self.lsn

    def _append(self, recs):
        with open(self.wal, "a", newline="\n") as f:
            for r in recs:
                line = json.dumps(r, sort_keys=True, separators=(",", ":"))
                f.write(f"{zlib.crc32(line.encode()):08x} {line}\n")
            f.flush()
            if self.sync: os.fsync(f.fileno())

    def apply(self, tid, legs):
        with self.mu:
            if not self.up: raise StoreDown("database is down")
            new = {}; steps = []
            for a, d in legs:
                cur = new.get(a, self.balances[a]); after = cur + d
                if after < 0: raise ValueError("insufficient funds")
                new[a] = after; steps.append((a, cur, after))
            recs = [{"lsn": self._next(), "t": "BEGIN", "tid": tid}]
            recs += [{"lsn": self._next(), "t": "UPD", "tid": tid, "acct": a, "before": b, "after": c} for a, b, c in steps]
            recs.append({"lsn": self._next(), "t": "COMMIT", "tid": tid})
            self._append(recs)                       # 1. log to disk  2. then change the data
            self.balances.update(new); self.committed += 1

    def checkpoint(self):
        with self.mu:
            _dump(self.snap, {"lsn": self.lsn, "balances": self.balances}); return self.lsn

    def total(self): return sum(self.balances.values())

    def simulate_crash(self, tid, legs, steal=True):
        """Crash in the middle of a transaction: BEGIN and UPD records are logged, no COMMIT.
        With steal=True the half-done balances are also written to the checkpoint file (dirty pages
        reached disk), so recovery really has something to undo."""
        with self.mu:
            recs = [{"lsn": self._next(), "t": "BEGIN", "tid": tid}]
            for a, d in legs:
                before = self.balances[a]; self.balances[a] = before + d
                recs.append({"lsn": self._next(), "t": "UPD", "tid": tid, "acct": a, "before": before, "after": before + d})
            self._append(recs)
            if steal: _dump(self.snap, {"lsn": self.lsn, "balances": self.balances})
            self.up, self.balances = False, None          # memory is lost

    def _read_wal(self):
        recs, good = [], 0; torn = False
        data = open(self.wal, "rb").read()
        for raw in data.split(b"\n")[:-1] if data.endswith(b"\n") else data.split(b"\n"):
            try:
                crc, line = raw.decode().split(" ", 1)
                if int(crc, 16) != zlib.crc32(line.encode()): raise ValueError
                recs.append(json.loads(line)); good += len(raw) + 1
            except Exception:
                torn = True; break
        if torn or good != len(data):
            with open(self.wal, "r+b") as f: f.truncate(good)      # cut off the torn tail
            torn = True
        return recs, torn

    def recover(self):
        """Analysis, redo (repeat history), undo losers. Returns a report."""
        t0 = time.perf_counter()
        recs, torn = self._read_wal(); snap = _load(self.snap); bal, snap_lsn = dict(snap["balances"]), snap["lsn"]
        state = {}
        for r in recs:
            if r["t"] == "BEGIN": state[r["tid"]] = "active"
            elif r["t"] == "COMMIT": state[r["tid"]] = "committed"
            elif r["t"] == "ABORT": state[r["tid"]] = "aborted"
        redo = 0
        for r in recs:
            if r["t"] == "UPD" and r["lsn"] > snap_lsn: bal[r["acct"]] = r["after"]; redo += 1
        losers = [t for t, s in state.items() if s == "active"]; undo = 0
        self.lsn = recs[-1]["lsn"] if recs else 0; clrs = []
        for r in reversed(recs):
            if r["t"] == "UPD" and state.get(r["tid"]) == "active":
                bal[r["acct"]] = r["before"]; undo += 1
                # compensation record: the undo itself is logged, so a repeated recovery stays correct
                clrs.append({"lsn": self._next(), "t": "UPD", "tid": r["tid"], "acct": r["acct"],
                             "before": r["after"], "after": r["before"], "clr": True})
        self.balances = bal; self.committed = sum(1 for s in state.values() if s == "committed")
        self.up = True
        if losers: self._append(clrs + [{"lsn": self._next(), "t": "ABORT", "tid": t} for t in losers])
        return {"log_records": len(recs), "torn_tail_removed": torn, "redone": redo, "undone": undo,
                "rolled_back_txns": losers, "committed_txns": self.committed,
                "seconds": round(time.perf_counter() - t0, 4)}

    # ----- backup and point-in-time restore
    def backup(self, dest):
        with self.mu:
            _dump(self.snap, {"lsn": self.lsn, "balances": self.balances})
            os.makedirs(dest, exist_ok=True); files = {}
            for p in (self.base, self.snap, self.wal):
                shutil.copy(p, dest); files[os.path.basename(p)] = _sha(p)
            _dump(os.path.join(dest, "manifest.json"), {"lsn": self.lsn, "time": time.time(), "sha256": files, "balances": {}})
            return self.lsn

    @staticmethod
    def restore(src, dest, until_lsn=None, **kw):
        """Verify checksums, then rebuild from the base copy by replaying committed transactions up to until_lsn."""
        man = json.load(open(os.path.join(src, "manifest.json")))
        for name, h in man["sha256"].items():
            if _sha(os.path.join(src, name)) != h: raise AuthError(f"backup file {name} failed its checksum")
        base = _load(os.path.join(src, "base.json")); bal = dict(base["balances"]); recs = []
        for line in open(os.path.join(src, "wal.log")).read().splitlines():
            crc, body = line.split(" ", 1)
            if int(crc, 16) != zlib.crc32(body.encode()): break
            recs.append(json.loads(body))
        limit = until_lsn if until_lsn is not None else (recs[-1]["lsn"] if recs else 0)
        win = {r["tid"] for r in recs if r["t"] == "COMMIT" and r["lsn"] <= limit}
        for r in recs:
            if r["t"] == "UPD" and r["tid"] in win and r["lsn"] <= limit: bal[r["acct"]] = r["after"]
        st = WalStore(dest, n_accounts=0, **kw); st.balances = bal; st.lsn = 0; st.committed = len(win)
        open(st.wal, "w").close(); _dump(st.base, {"lsn": 0, "balances": bal}); _dump(st.snap, {"lsn": 0, "balances": bal})
        st.initial_total = sum(base["balances"].values()); return st


# ===================================================================== SECURITY
ROLES = {"customer": {"transfer:own", "view:own"},
         "teller": {"transfer:any", "view:any"},
         "auditor": {"view:any", "audit:read"},
         "admin": {"view:any", "audit:read", "backup", "restore", "checkpoint"}}

class UserStore:
    """Salted PBKDF2 password hashes, lockout after repeated failures, signed expiring session tokens."""
    def __init__(self, max_fail=5, lock_s=60, ttl=900, iters=100_000):
        self.users, self.secret, self.mu = {}, secrets.token_bytes(32), threading.Lock()
        self.max_fail, self.lock_s, self.ttl, self.iters = max_fail, lock_s, ttl, iters
    def _hash(self, pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, self.iters)
    def add(self, name, pw, role, owns=()):
        salt = secrets.token_bytes(16)
        self.users[name] = {"salt": salt, "hash": self._hash(pw, salt), "role": role, "owns": set(owns), "fails": 0, "until": 0}
    def login(self, name, pw):
        with self.mu:
            u = self.users.get(name)
            if u is None: self._hash(pw, b"x" * 16); raise AuthError("invalid credentials")     # equal work, no user hint
            if time.time() < u["until"]: raise AuthError("account locked after repeated failures")
            if not hmac.compare_digest(self._hash(pw, u["salt"]), u["hash"]):
                u["fails"] += 1
                if u["fails"] >= self.max_fail: u["until"], u["fails"] = time.time() + self.lock_s, 0
                raise AuthError("invalid credentials")
            u["fails"] = 0
        return self._token(name)
    def _token(self, name):
        payload = f"{name}|{time.time() + self.ttl}".encode()
        return base64.urlsafe_b64encode(payload).decode() + "." + hmac.new(self.secret, payload, "sha256").hexdigest()
    def get(self, name):
        """{'role': ..., 'owns': set(...)} or None. Bank uses this instead of reading the user table directly."""
        return self.users.get(name)
    def credential(self, name):
        """(salt, hash) as stored: lets tests show that no plaintext password is kept."""
        return self.users[name]["salt"], self.users[name]["hash"]
    def verify(self, token):
        try:
            p64, sig = token.rsplit(".", 1); payload = base64.urlsafe_b64decode(p64)
            if not hmac.compare_digest(hmac.new(self.secret, payload, "sha256").hexdigest(), sig): raise ValueError
            name, exp = payload.decode().split("|")
            if float(exp) < time.time(): raise AuthError("session expired")
            return name
        except AuthError: raise
        except Exception: raise AuthError("invalid session token")


class AuditLog:
    """Append-only, hash-chained: each entry includes the hash of the previous one, so editing or
    deleting any past entry breaks every hash after it."""
    def __init__(self, path):
        self.path, self.mu, self.prev, self.seq = path, threading.Lock(), "0" * 64, 0
        open(path, "w").close()
    def add(self, user, action, detail, result):
        with self.mu:
            self.seq += 1
            e = {"seq": self.seq, "ts": round(time.time(), 3), "user": user, "action": action, "detail": detail, "result": result, "prev": self.prev}
            e["hash"] = hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest(); self.prev = e["hash"]
            with open(self.path, "a") as f: f.write(json.dumps(e, sort_keys=True) + "\n")
    def entries(self): return [json.loads(l) for l in open(self.path)]
    def _tamper(self, seq, result="OK (edited)"):
        """Test/demo only: edit one stored entry behind the log's back. verify() must detect it."""
        lines = open(self.path).read().splitlines(); e = json.loads(lines[seq - 1]); e["result"] = result
        lines[seq - 1] = json.dumps(e, sort_keys=True); open(self.path, "w").write("\n".join(lines) + "\n")
    def verify(self):
        prev = "0" * 64
        for e in self.entries():
            h = e.pop("hash")
            if e["prev"] != prev or hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest() != h:
                return False, e["seq"]
            prev = h
        return True, None


class PgUserStore(UserStore):
    """Same behaviour as UserStore, but users, roles and account ownership are rows in PostgreSQL
    (app_users, user_accounts). The lockout counter is updated under a row lock, so concurrent wrong
    passwords cannot slip past the limit. Session tokens are still signed with an in-memory secret."""
    def __init__(self, **kw):
        super().__init__(**kw); self.users = None
    def add(self, name, pw, role, owns=()):
        salt = secrets.token_bytes(16); h = self._hash(pw, salt)
        with pg_store.pooled_session() as cur:
            cur.execute("""INSERT INTO app_users(username, role_name, password_salt, password_hash, pbkdf2_iterations)
                           VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT (username) DO UPDATE SET role_name = EXCLUDED.role_name,
                             password_salt = EXCLUDED.password_salt, password_hash = EXCLUDED.password_hash,
                             pbkdf2_iterations = EXCLUDED.pbkdf2_iterations, failed_attempts = 0, locked_until = NULL""",
                        (name, role, salt, h, self.iters))
            cur.execute("DELETE FROM user_accounts WHERE username = %s", (name,))
            for a in owns: cur.execute("INSERT INTO user_accounts(username, account_id) VALUES (%s,%s)", (name, a))
    def get(self, name):
        with pg_store.pooled_session() as cur:
            cur.execute("""SELECT u.role_name, COALESCE(array_agg(a.account_id) FILTER (WHERE a.account_id IS NOT NULL), '{}')
                           FROM app_users u LEFT JOIN user_accounts a USING (username)
                           WHERE u.username = %s GROUP BY u.role_name""", (name,))
            row = cur.fetchone()
        return None if row is None else {"role": row[0], "owns": set(row[1])}
    def credential(self, name):
        with pg_store.pooled_session() as cur:
            cur.execute("SELECT password_salt, password_hash FROM app_users WHERE username = %s", (name,))
            salt, h = cur.fetchone()
        return bytes(salt), bytes(h)
    def login(self, name, pw):
        err = None
        with pg_store.pooled_session() as cur:
            cur.execute("""SELECT password_salt, password_hash, pbkdf2_iterations, failed_attempts,
                                  COALESCE(locked_until > now(), false)
                           FROM app_users WHERE username = %s FOR UPDATE""", (name,))
            row = cur.fetchone()
            if row is None:
                self._hash(pw, b"x" * 16); err = "invalid credentials"        # equal work, no user hint
            else:
                salt, stored, iters, fails, locked = bytes(row[0]), bytes(row[1]), row[2], row[3], row[4]
                if locked:
                    err = "account locked after repeated failures"
                else:
                    given = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iters)
                    if hmac.compare_digest(given, stored):
                        cur.execute("UPDATE app_users SET failed_attempts = 0 WHERE username = %s", (name,))
                    else:
                        err = "invalid credentials"
                        if fails + 1 >= self.max_fail:
                            cur.execute("""UPDATE app_users SET failed_attempts = 0,
                                           locked_until = now() + make_interval(secs => %s) WHERE username = %s""",
                                        (self.lock_s, name))
                        else:
                            cur.execute("UPDATE app_users SET failed_attempts = %s WHERE username = %s", (fails + 1, name))
        if err: raise AuthError(err)                  # raised after the commit, so the failure count is kept
        return self._token(name)


class PgAuditLog(AuditLog):
    """Hash-chained audit log stored in the audit_log table. One chain per Bank directory (so a restarted Bank
    resumes its chain). A per-chain advisory lock makes 'read last hash, insert next entry' atomic across threads
    and processes. verify() is inherited: it recomputes every hash from the stored columns."""
    def __init__(self, chain):
        self.chain = chain
    @property
    def seq(self):
        with pg_store.pooled_session() as cur:
            cur.execute("SELECT COALESCE(MAX(seq), 0) FROM audit_log WHERE chain = %s", (self.chain,))
            return cur.fetchone()[0]
    def add(self, user, action, detail, result):
        with pg_store.pooled_session() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (self.chain,))
            cur.execute("SELECT seq, entry_hash FROM audit_log WHERE chain = %s ORDER BY seq DESC LIMIT 1", (self.chain,))
            last = cur.fetchone(); seq, prev = (last[0] + 1, last[1]) if last else (1, "0" * 64)
            e = {"seq": seq, "ts": round(time.time(), 3), "user": user, "action": action, "detail": detail,
                 "result": result, "prev": prev}
            h = hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest()
            cur.execute("""INSERT INTO audit_log(chain, seq, ts, username, action, detail, result, prev_hash, entry_hash)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (self.chain, seq, e["ts"], user, action, detail, result, prev, h))
    def entries(self):
        with pg_store.pooled_session() as cur:
            cur.execute("""SELECT seq, ts, username, action, detail, result, prev_hash, entry_hash FROM audit_log
                           WHERE chain = %s ORDER BY seq""", (self.chain,))
            return [{"seq": r[0], "ts": r[1], "user": r[2], "action": r[3], "detail": r[4], "result": r[5],
                     "prev": r[6], "hash": r[7]} for r in cur.fetchall()]
    def _tamper(self, seq, result="OK (edited)"):
        """Test/demo only: edit a stored entry as a database administrator could (switching the append-only
        trigger off first). verify() must still detect it."""
        with pg_store.pooled_session() as cur:
            cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change")
            cur.execute("UPDATE audit_log SET result = %s WHERE chain = %s AND seq = %s", (result, self.chain, seq))
            cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change")


# ================================================== BANK: DBMS + OS layer together
class Bank:
    """Every transfer: authenticate, authorise, validate, deduplicate, admit (Banker's + ML gate),
    lock accounts, write-ahead log, commit, audit."""
    def __init__(self, path, predictor=None, mode="banker", n_accounts=100, sync=True,
                 per_txn_limit=50_000, daily_limit=200_000):
        self.path = path; self.store = WalStore(os.path.join(path, "db"), n_accounts, sync=sync)
        self.lm = LockManager(mode, 2.0); self.adm = Admission(self.lm, predictor)
        if pg_store.enabled():
            self.roles = pg_store.load_roles()
            if not self.roles: raise RuntimeError("roles table is empty: run seed_postgres.py first")
            self.users, self.audit = PgUserStore(), PgAuditLog(os.path.abspath(path))
        else:
            self.roles, self.users, self.audit = ROLES, UserStore(), AuditLog(os.path.join(path, "audit.log"))
        self.limits, self.n_accounts = (per_txn_limit, daily_limit), n_accounts
        self.mu, self.done, self.daily, self.tid = threading.Lock(), {}, {}, itertools.count(1)

    def login(self, name, pw):
        try:
            t = self.users.login(name, pw); self.audit.add(name, "login", "", "OK"); return t
        except AuthError as e:
            self.audit.add(name, "login", "", f"FAILED: {e}"); raise

    def _deny(self, user, detail, why):
        self.audit.add(user, "transfer", detail, "DENIED: " + why); return {"ok": False, "status": "DENIED: " + why}

    def transfer(self, token, src, dst, amount, idem=None, prio=2):
        try: user = self.users.verify(token)
        except AuthError as e: return self._deny("?", f"{src}->{dst} {amount}", str(e))
        u, detail = self.users.get(user), f"{src}->{dst} {amount}"
        if u is None: return self._deny(user, detail, "unknown user")
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (src, dst, amount)):
            return self._deny(user, detail, "inputs must be integers")          # blocks injection-style input
        if not (0 <= src < self.n_accounts and 0 <= dst < self.n_accounts) or src == dst or amount <= 0:
            return self._deny(user, detail, "invalid accounts or amount")
        perms = self.roles[u["role"]]
        if not ("transfer:any" in perms or ("transfer:own" in perms and src in u["owns"])):
            return self._deny(user, detail, "role or ownership does not allow this transfer")
        if amount > self.limits[0]: return self._deny(user, detail, "per-transaction limit exceeded")
        day = time.strftime("%Y-%m-%d")
        with self.mu:
            if idem is not None:
                if idem in self.done: return {**self.done[idem], "status": "DUPLICATE (ignored)", "ok": False}
                self.done[idem] = {"status": "IN PROGRESS"}
            d = self.daily.get(user, (day, 0))
            if d[0] != day: d = (day, 0)
            if d[1] + amount > self.limits[1]:
                if idem is not None: self.done.pop(idem, None)
                return self._deny(user, detail, "daily limit exceeded")
        tid, plan, t0 = next(self.tid), [src, dst], time.monotonic()
        f, risk = self.adm.admit(plan, prio, t0); status = "FAILED: too many aborts"
        for attempt in range(6):
            self.lm.register(tid, plan, prio)
            try:
                for a in plan: self.lm.acquire(tid, a)
                self.store.apply(tid, [(src, -amount), (dst, amount)]); status = "COMMITTED"
            except Abort: time.sleep(0.005 * (attempt + 1)); continue
            except ValueError as e: status = "REJECTED: " + str(e)
            except StoreDown: status = "FAILED: database down"
            finally: self.lm.unregister(tid)
            break
        with self.mu:
            if status == "COMMITTED": self.daily[user] = (day, d[1] + amount)
            res = {"ok": status == "COMMITTED", "status": status, "tid": tid, "risk": None if risk is None else round(risk, 3)}
            if idem is not None: self.done[idem] = res
        self.audit.add(user, "transfer", detail, status); return res

    def admin(self, token, action, **kw):
        user = self.users.verify(token)
        if action not in self.roles[self.users.get(user)["role"]]:
            self.audit.add(user, action, "", "DENIED: not permitted"); raise Forbidden(f"role cannot {action}")
        out = {"checkpoint": lambda: self.store.checkpoint(), "backup": lambda: self.store.backup(kw["dest"])}[action]()
        self.audit.add(user, action, str(kw), "OK"); return out
