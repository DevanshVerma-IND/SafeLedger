"""
SafeLedger - OS Layer (standalone evaluation build)
===================================================
Runs with plain Python 3.8+, no external packages:   python os_layer.py

What it demonstrates (one section each):
  1. CPU scheduling of transactions  : FCFS vs Round Robin vs Priority (with aging)
  2. Process synchronization         : race condition without a lock, fixed with Lock;
                                       Semaphore limiting concurrent transactions
  3. Deadlock detection              : lock manager + Wait-For Graph + victim selection
  4. Deadlock avoidance              : Banker's Algorithm (textbook case + banking case)
  5. ML hook                         : Banker's decision combined with the risk score
                                       from the Flask /predict service (optional)

Every section ends with self-checks so the output reads as PASS / FAIL.
"""
import json
import threading
import time
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))
    print(f"   [{'PASS' if condition else 'FAIL'}] {name}")


def heading(text):
    print("\n" + "=" * 72 + f"\n{text}\n" + "=" * 72)


# ---------------------------------------------------------------------------
# 1. SCHEDULER
# ---------------------------------------------------------------------------
@dataclass
class Txn:
    tid: str
    arrival: int
    burst: int       # estimated processing cost of the transaction
    priority: int    # lower number = higher priority


def _metrics(name, txns, completion, slices=None):
    rows = []
    for t in txns:
        turnaround = completion[t.tid] - t.arrival
        rows.append((t.tid, completion[t.tid], turnaround, turnaround - t.burst))
    span = max(completion.values()) - min(t.arrival for t in txns)
    return {
        "name": name,
        "rows": rows,
        "avg_wait": sum(r[3] for r in rows) / len(rows),
        "avg_tat": sum(r[2] for r in rows) / len(rows),
        "throughput": len(txns) / span,
        "switches": (slices - 1) if slices else len(txns) - 1,
        "order": [tid for tid, *_ in sorted(rows, key=lambda r: r[1])],
    }


def fcfs(txns):
    now, done = 0, {}
    for t in sorted(txns, key=lambda x: (x.arrival, x.tid)):
        now = max(now, t.arrival) + t.burst
        done[t.tid] = now
    return _metrics("FCFS", txns, done)


def round_robin(txns, quantum=3):
    pending = sorted(txns, key=lambda x: (x.arrival, x.tid))
    remaining = {t.tid: t.burst for t in txns}
    ready, done = deque(), {}
    now = i = slices = 0

    def admit():
        nonlocal i
        while i < len(pending) and pending[i].arrival <= now:
            ready.append(pending[i])
            i += 1

    admit()
    while len(done) < len(txns):
        if not ready:
            now = pending[i].arrival
            admit()
            continue
        t = ready.popleft()
        run = min(quantum, remaining[t.tid])
        now += run
        slices += 1
        remaining[t.tid] -= run
        admit()                      # newcomers queue ahead of the preempted txn
        if remaining[t.tid] == 0:
            done[t.tid] = now
        else:
            ready.append(t)
    return _metrics(f"Round Robin (q={quantum})", txns, done, slices)


def priority_sched(txns, aging_interval=5):
    """Non-preemptive priority. Every `aging_interval` units a txn waits, its
    effective priority improves by one step, so low-priority txns cannot starve."""
    pending, done, now = list(txns), {}, 0
    while pending:
        arrived = [t for t in pending if t.arrival <= now]
        if not arrived:
            now = min(t.arrival for t in pending)
            continue
        pick = min(arrived, key=lambda t: (t.priority - (now - t.arrival) // aging_interval,
                                           t.arrival, t.tid))
        now += pick.burst
        done[pick.tid] = now
        pending.remove(pick)
    return _metrics(f"Priority + aging (every {aging_interval})", txns, done)


def section_scheduler():
    heading("1. CPU SCHEDULING OF TRANSACTIONS")
    workload = [
        Txn("T1", 0, 8, 3), Txn("T2", 1, 4, 1), Txn("T3", 2, 9, 4),
        Txn("T4", 3, 5, 2), Txn("T5", 4, 2, 1),
    ]
    results = [fcfs(workload), round_robin(workload, 3), priority_sched(workload)]
    print(f"   {'Algorithm':<30}{'Avg wait':>9}{'Avg TAT':>9}{'Thrput':>9}{'Switches':>10}   Order")
    for r in results:
        print(f"   {r['name']:<30}{r['avg_wait']:>9.2f}{r['avg_tat']:>9.2f}"
              f"{r['throughput']:>9.3f}{r['switches']:>10}   {' '.join(r['order'])}")
    fc, rr, pr = results
    check("every algorithm finishes all 5 transactions",
          all(len(r["rows"]) == 5 for r in results))
    check("priority scheduling serves the urgent T2 before bulky T3", pr["order"].index("T2") < pr["order"].index("T3"))
    check("round robin gives the short T5 a lower wait than FCFS",
          dict((r[0], r[3]) for r in rr["rows"])["T5"] < dict((r[0], r[3]) for r in fc["rows"])["T5"])


# ---------------------------------------------------------------------------
# 2. SYNCHRONISATION
# ---------------------------------------------------------------------------
def race_demo(use_lock, workers=4, ops=300):
    state, lock = {"balance": 0}, threading.Lock()

    def deposit_loop():
        for _ in range(ops):
            if use_lock:
                with lock:
                    b = state["balance"]
                    time.sleep(0)               # forces a thread switch mid read-modify-write
                    state["balance"] = b + 1
            else:
                b = state["balance"]
                time.sleep(0)
                state["balance"] = b + 1

    threads = [threading.Thread(target=deposit_loop) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return state["balance"], workers * ops


def semaphore_demo(limit=3, txn_count=12):
    gate = threading.BoundedSemaphore(limit)
    meter, peak, running = threading.Lock(), [0], [0]

    def txn():
        with gate:
            with meter:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.01)
            with meter:
                running[0] -= 1

    threads = [threading.Thread(target=txn) for _ in range(txn_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return peak[0]


def section_sync():
    heading("2. PROCESS SYNCHRONISATION")
    got, expected = race_demo(use_lock=False)
    print(f"   Without lock : final balance {got}, expected {expected}, lost updates {expected - got}")
    got_l, expected_l = race_demo(use_lock=True)
    print(f"   With Lock    : final balance {got_l}, expected {expected_l}, lost updates {expected_l - got_l}")
    check("mutex keeps the balance exact (no lost updates)", got_l == expected_l)
    check("race condition is visible when the lock is removed", got < expected)
    peak = semaphore_demo(limit=3)
    print(f"   Semaphore(3) : 12 transactions launched, peak concurrency observed = {peak}")
    check("semaphore never lets more than 3 transactions run at once", peak <= 3)


# ---------------------------------------------------------------------------
# 3. LOCK MANAGER + WAIT-FOR GRAPH
# ---------------------------------------------------------------------------
class LockManager:
    """Exclusive account locks with FIFO wait queues. Non-blocking on purpose:
    request() returns GRANTED / WAITING so deadlocks can be reproduced and
    resolved deterministically (real threads would simply hang)."""

    def __init__(self):
        self.holder = {}                     # resource -> tid
        self.queue = defaultdict(list)       # resource -> waiting tids (FIFO)
        self.held = defaultdict(set)         # tid -> resources
        self.priority = {}                   # tid -> priority (lower = more important)
        self.contention = defaultdict(int)   # resource -> times a request had to wait
        self.log = []

    def register(self, tid, priority):
        self.priority[tid] = priority

    def request(self, tid, res):
        owner = self.holder.get(res)
        if owner is None or owner == tid:
            self.holder[res] = tid
            self.held[tid].add(res)
            self.log.append(f"{tid} locks {res}")
            return "GRANTED"
        self.queue[res].append(tid)
        self.contention[res] += 1
        self.log.append(f"{tid} waits for {res} (held by {owner})")
        return "WAITING"

    def wait_for_graph(self):
        graph = defaultdict(set)
        for res, waiters in self.queue.items():
            owner = self.holder.get(res)
            for w in waiters:
                if owner is not None and owner != w:
                    graph[w].add(owner)
        return graph

    def find_cycle(self):
        graph, colour, path = self.wait_for_graph(), {}, []

        def dfs(u):
            colour[u] = 1
            path.append(u)
            for v in sorted(graph.get(u, ())):
                if colour.get(v, 0) == 0:
                    found = dfs(v)
                    if found:
                        return found
                elif colour[v] == 1:
                    return path[path.index(v):] + [v]
            path.pop()
            colour[u] = 2
            return None

        for node in sorted(graph):
            if colour.get(node, 0) == 0:
                cycle = dfs(node)
                if cycle:
                    return cycle
        return None

    def release_all(self, tid):
        for res in list(self.held[tid]):
            del self.holder[res]
            self.held[tid].discard(res)
            while self.queue[res]:           # hand the lock to the next live waiter
                nxt = self.queue[res].pop(0)
                if nxt != tid:
                    self.holder[res] = nxt
                    self.held[nxt].add(res)
                    self.log.append(f"{nxt} now locks {res}")
                    break
        for res in self.queue:               # a victim must not keep waiting anywhere
            self.queue[res] = [w for w in self.queue[res] if w != tid]

    def resolve_deadlocks(self):
        """Abort the lowest-priority transaction in each cycle until none remain."""
        victims = []
        while True:
            cycle = self.find_cycle()
            if not cycle:
                return victims
            members = set(cycle)
            victim = max(members, key=lambda t: (self.priority[t], t))
            self.log.append(f"cycle {' -> '.join(cycle)}; aborting {victim}")
            self.release_all(victim)
            victims.append(victim)

    def features(self, tid, res, wait_ms=0):
        """Same five fields the Random Forest expects (see ML hook below)."""
        owner = self.holder.get(res)
        return {
            "locks_held_on_target": len(self.held[owner]) if owner else 0,
            "wait_queue_length": len(self.queue[res]),
            "account_contention_count": self.contention[res],
            "wait_time_ms": wait_ms,
            "priority": self.priority[tid],
        }


def section_deadlock():
    heading("3. DEADLOCK DETECTION (Wait-For Graph)")
    lm = LockManager()
    lm.register("T1", 1)   # high priority
    lm.register("T2", 3)   # low priority -> expected victim
    lm.request("T1", "ACC_A")
    lm.request("T2", "ACC_B")
    lm.request("T1", "ACC_B")   # T1 -> T2
    lm.request("T2", "ACC_A")   # T2 -> T1  (cycle)
    graph = {k: sorted(v) for k, v in lm.wait_for_graph().items()}
    print(f"   Wait-For Graph : {graph}")
    cycle = lm.find_cycle()
    print(f"   Cycle found    : {' -> '.join(cycle) if cycle else 'none'}")
    check("opposite-order transfers create a cycle", cycle is not None and set(cycle) == {"T1", "T2"})
    victims = lm.resolve_deadlocks()
    print(f"   Victim aborted : {victims}")
    print(f"   Lock owners now: {dict(lm.holder)}")
    check("lowest-priority transaction (T2) is the victim", victims == ["T2"])
    check("no cycle remains after recovery", lm.find_cycle() is None)
    check("T1 got ACC_B after the victim released it", lm.holder.get("ACC_B") == "T1")

    # three-way cycle: T1->T2->T3->T1
    lm3 = LockManager()
    for tid, p in (("T1", 2), ("T2", 2), ("T3", 5)):
        lm3.register(tid, p)
    for tid, res in (("T1", "A"), ("T2", "B"), ("T3", "C")):
        lm3.request(tid, res)
    lm3.request("T1", "B")
    lm3.request("T2", "C")
    lm3.request("T3", "A")
    check("three-transaction cycle is detected", lm3.find_cycle() is not None)
    check("three-way cycle resolved by aborting only T3", lm3.resolve_deadlocks() == ["T3"])

    # ordered locking prevents the cycle in the first place
    lm_o = LockManager()
    lm_o.register("T1", 1)
    lm_o.register("T2", 1)
    for tid in ("T1", "T2"):
        for res in sorted(["ACC_A", "ACC_B"]):   # both always lock in ascending order
            lm_o.request(tid, res)
    check("ascending lock order never produces a cycle", lm_o.find_cycle() is None)


# ---------------------------------------------------------------------------
# 4. BANKER'S ALGORITHM
# ---------------------------------------------------------------------------
class Banker:
    def __init__(self, total, max_demand, allocation):
        self.total = list(total)
        self.max = {p: list(v) for p, v in max_demand.items()}
        self.alloc = {p: list(v) for p, v in allocation.items()}

    def available(self):
        used = [sum(a[j] for a in self.alloc.values()) for j in range(len(self.total))]
        return [self.total[j] - used[j] for j in range(len(self.total))]

    def need(self, p):
        return [m - a for m, a in zip(self.max[p], self.alloc[p])]

    def is_safe(self):
        work, finished, order = self.available(), set(), []
        progressed = True
        while progressed and len(finished) < len(self.max):
            progressed = False
            for p in self.max:
                if p not in finished and all(n <= w for n, w in zip(self.need(p), work)):
                    work = [w + a for w, a in zip(work, self.alloc[p])]
                    finished.add(p)
                    order.append(p)
                    progressed = True
        return len(finished) == len(self.max), order

    def request(self, p, req):
        """Returns (granted, reason). State is rolled back unless the grant is safe."""
        if any(r > n for r, n in zip(req, self.need(p))):
            return False, "exceeds the maximum it declared"
        if any(r > a for r, a in zip(req, self.available())):
            return False, "resources not available right now"
        self.alloc[p] = [a + r for a, r in zip(self.alloc[p], req)]
        safe, order = self.is_safe()
        if safe:
            return True, "safe, sequence " + "->".join(order)
        self.alloc[p] = [a - r for a, r in zip(self.alloc[p], req)]
        return False, "would leave the system in an UNSAFE state"


def section_banker():
    heading("4. DEADLOCK AVOIDANCE (Banker's Algorithm)")
    print("   a) Textbook case: 5 processes, 3 resource types")
    b = Banker(
        total=[10, 5, 7],
        max_demand={"P0": [7, 5, 3], "P1": [3, 2, 2], "P2": [9, 0, 2], "P3": [2, 2, 2], "P4": [4, 3, 3]},
        allocation={"P0": [0, 1, 0], "P1": [2, 0, 0], "P2": [3, 0, 2], "P3": [2, 1, 1], "P4": [0, 0, 2]},
    )
    safe, order = b.is_safe()
    print(f"      initial state safe: {safe}, sequence: {' -> '.join(order)}")
    check("initial state is safe with sequence P1,P3,P4,P0,P2", safe and order == ["P1", "P3", "P4", "P0", "P2"])
    ok, why = b.request("P1", [1, 0, 2])
    print(f"      P1 requests [1,0,2] -> {'GRANT' if ok else 'DENY'} ({why})")
    check("P1 [1,0,2] is granted", ok)
    ok, why = b.request("P4", [3, 3, 0])
    print(f"      P4 requests [3,3,0] -> {'GRANT' if ok else 'DENY'} ({why})")
    check("P4 [3,3,0] is denied (not available)", not ok)
    ok, why = b.request("P0", [0, 2, 0])
    print(f"      P0 requests [0,2,0] -> {'GRANT' if ok else 'DENY'} ({why})")
    check("P0 [0,2,0] is denied (unsafe)", not ok)

    print("   b) Banking case: two transfers, two accounts (one lock each)")
    bank = Banker(total=[1, 1],                       # columns: ACC_A, ACC_B
                  max_demand={"T1": [1, 1], "T2": [1, 1]},
                  allocation={"T1": [1, 0], "T2": [0, 0]})     # T1 already holds ACC_A
    ok, why = bank.request("T2", [0, 1])
    print(f"      T2 asks for ACC_B while T1 holds ACC_A -> {'GRANT' if ok else 'DENY'} ({why})")
    check("T2 is refused ACC_B because it would create a deadlock-prone state", not ok)
    ok, why = bank.request("T1", [0, 1])
    print(f"      T1 asks for ACC_B                      -> {'GRANT' if ok else 'DENY'} ({why})")
    check("T1 may take ACC_B and finish first", ok)


# ---------------------------------------------------------------------------
# 5. ML HOOK
# ---------------------------------------------------------------------------
def get_risk_score(features, url="http://localhost:5000/predict", timeout=0.05):
    """Calls the Flask service. Returns None when it is down or slow, so the
    OS layer degrades to its rule-based behaviour instead of freezing."""
    try:
        req = urllib.request.Request(url, data=json.dumps(features).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return float(json.loads(resp.read())["risk_score"])
    except Exception:
        return None


def admit(banker_safe, risk, threshold=0.5):
    if not banker_safe:
        return "DENY"        # rule-based safety always wins
    if risk is not None and risk >= threshold:
        return "DELAY"       # predicted risky: wait a little, deadlock never forms
    return "GRANT"


def section_ml_hook():
    heading("5. ML HOOK (Banker's decision + Random Forest risk score)")
    lm = LockManager()
    lm.register("T1", 1)
    lm.register("T2", 2)
    lm.request("T1", "ACC_A")
    lm.request("T2", "ACC_A")
    feats = lm.features("T2", "ACC_A", wait_ms=120)
    print(f"   Feature vector for the ML service: {feats}")
    check("feature vector has the five fields the classifier expects",
          set(feats) == {"locks_held_on_target", "wait_queue_length", "account_contention_count",
                         "wait_time_ms", "priority"})
    live = get_risk_score(feats)
    print(f"   Live /predict score: {live if live is not None else 'service not reachable -> fallback'}")
    check("unreachable ML service yields None instead of raising", live is None or 0 <= live <= 1)
    cases = [("Banker safe, risk 0.12", True, 0.12, "GRANT"),
             ("Banker safe, risk 0.83", True, 0.83, "DELAY"),
             ("Banker unsafe, risk 0.05", False, 0.05, "DENY"),
             ("Banker safe, ML down", True, None, "GRANT")]
    for label, safe, risk, expected in cases:
        got = admit(safe, risk)
        print(f"   {label:<28} -> {got}")
        check(f"decision for '{label}' is {expected}", got == expected)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("SafeLedger OS layer - evaluation run")
    section_scheduler()
    section_sync()
    section_deadlock()
    section_banker()
    section_ml_hook()
    passed = sum(ok for _, ok in RESULTS)
    heading(f"SUMMARY: {passed}/{len(RESULTS)} checks passed")
    raise SystemExit(0 if passed == len(RESULTS) else 1)
