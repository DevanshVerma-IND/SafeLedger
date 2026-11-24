"""DBMS-layer checks: recovery and security. Run: python dbms_selftest.py"""
import json, os, shutil, tempfile, threading, time
from dbms import *
import pg_store
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("[PASS] " if cond else "[FAIL] ") + name)

def new_bank(**kw):
    b = Bank(tempfile.mkdtemp(), n_accounts=30, **kw)
    b.users.add("alice", "pw-a", "customer", owns=[1, 2]); b.users.add("bob", "pw-b", "customer", owns=[3])
    b.users.add("teller", "pw-t", "teller"); b.users.add("auditor", "pw-u", "auditor"); b.users.add("admin", "pw-x", "admin")
    return b

print("--- recovery")
b = new_bank(sync=False); tt = b.login("teller", "pw-t"); S = b.store; T0 = S.total()
def worker(k):
    for i in range(25): b.transfer(tt, (k * 3 + i) % 10, (k * 3 + i + 1) % 10, 5)
th = [threading.Thread(target=worker, args=(k,)) for k in range(8)]; [t.start() for t in th]; [t.join() for t in th]
check("200 concurrent transfers through the full path conserve money", S.total() == T0 and S.committed == 200)
before = dict(S.balances); S.simulate_crash(9001, [(4, -700), (5, 700)]); check("memory lost after crash", S.balances is None)
rep = S.recover()
check("recovery: committed work survives, half-done transaction undone", S.balances == before and rep["undone"] == 2 and 9001 in rep["rolled_back_txns"])
check("recovery is repeatable (second recovery changes nothing)", S.recover()["undone"] == 0 and S.balances == before)
S.checkpoint(); b.transfer(tt, 0, 1, 7); after_ckpt = dict(S.balances); S.simulate_crash(9002, [(6, -1), (7, 1)], steal=False)
rep = S.recover(); check("checkpoint: only the log after it is redone", rep["redone"] <= 5 and S.balances == after_ckpt)
with open(S.wal, "ab") as f: f.write(b"0000dead {\"lsn\": 99999, \"t\": \"UPD\", \"tid\": 5, \"acc")   # torn half-written record
S.simulate_crash(9003, [(8, -2), (9, 2)], steal=False)
rep = S.recover(); check("torn / corrupt log tail detected by CRC and discarded", rep["torn_tail_removed"] and S.balances == after_ckpt)
print("--- backup and point-in-time restore")
S2 = new_bank(sync=False); tk = S2.login("teller", "pw-t")
for i in range(10): S2.transfer(tk, 0, 1, 10)
mid = S2.store.lsn; mid_balance = S2.store.balances[1]
for i in range(10): S2.transfer(tk, 0, 1, 10)
bk = tempfile.mkdtemp(); S2.store.backup(bk)
r_full = WalStore.restore(bk, tempfile.mkdtemp(), sync=False); r_pit = WalStore.restore(bk, tempfile.mkdtemp(), until_lsn=mid, sync=False)
check("restore from backup reproduces the final state", r_full.balances == S2.store.balances)
check(f"point-in-time restore to LSN {mid} returns the earlier state", r_pit.balances[1] == mid_balance and r_pit.total() == r_pit.initial_total)
with open(os.path.join(bk, "wal.log"), "a") as f: f.write("x")
try: WalStore.restore(bk, tempfile.mkdtemp()); check("tampered backup rejected by checksum", False)
except AuthError: check("tampered backup rejected by checksum", True)
print("--- security")
b = new_bank(sync=False); ta, tb_, tt, tu, tx = (b.login(n, p) for n, p in [("alice", "pw-a"), ("bob", "pw-b"), ("teller", "pw-t"), ("auditor", "pw-u"), ("admin", "pw-x")])
salt, pwhash = b.users.credential("alice")
check("passwords stored as salted PBKDF2 hashes, never plaintext", b"pw-a" not in pwhash and len(salt) == 16)
check("customer can move money from own account", b.transfer(ta, 1, 5, 50)["ok"])
check("customer cannot move money from someone else's account", b.transfer(ta, 3, 5, 50)["status"].startswith("DENIED"))
check("auditor (read-only role) cannot transfer", b.transfer(tu, 1, 5, 50)["status"].startswith("DENIED"))
check("teller can transfer between any accounts", b.transfer(tt, 3, 5, 50)["ok"])
check("injection-style input is rejected", b.transfer(ta, "1; DROP TABLE accounts", 5, 50)["status"].startswith("DENIED"))
check("per-transaction limit enforced", b.transfer(tt, 1, 5, 60_000)["status"].startswith("DENIED"))
r1 = b.transfer(ta, 1, 5, 10, idem="pay-1"); r2 = b.transfer(ta, 1, 5, 10, idem="pay-1")
check("duplicate request (same idempotency key) applied once", r1["ok"] and "DUPLICATE" in r2["status"])
check("forged session token rejected", b.transfer(ta[:-4] + "0000", 1, 5, 1)["status"].startswith("DENIED"))
for _ in range(5):
    try: b.login("bob", "wrong")
    except AuthError: pass
try: b.login("bob", "pw-b"); check("account locks after 5 wrong passwords", False)
except AuthError as e: check("account locks after 5 wrong passwords", "locked" in str(e))
try: b.admin(ta, "backup", dest="x"); check("customer cannot run admin actions", False)
except Forbidden: check("customer cannot run admin actions", True)
check("admin can checkpoint", isinstance(b.admin(tx, "checkpoint"), int))
good, bad = b.audit.verify(); check(f"audit log chain intact ({b.audit.seq} entries)", good)
if pg_store.enabled():
    try: 
        with pg_store.pooled_session() as cur: cur.execute("UPDATE audit_log SET result = 'x' WHERE chain = %s", (b.audit.chain,))
        check("database refuses to edit audit_log (append-only trigger)", False)
    except Exception as e: check("database refuses to edit audit_log (append-only trigger)", "append-only" in str(e))
b.audit._tamper(4); good, bad = b.audit.verify()
check(f"tampering with an audit entry is detected (first bad entry {bad})", (not good) and bad == 4)
print("ALL PASSED" if ok else "SOME FAILED"); raise SystemExit(0 if ok else 1)
