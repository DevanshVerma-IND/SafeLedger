# SafeLedger — A Secure AI Banking Assistant

SafeLedger is an academic PBL fintech project demonstrating database management system (DBMS) ACID durability, operating system (OS) concurrency control & scheduling, and predictive machine learning (ML) admission gating.

---

## Quickstart (Installation & Verification)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run All Automated Test Suites
```bash
# Core engine correctness (15s)
python selftest.py

# DBMS crash recovery (ARIES), WAL, and security checks (10s)
python dbms_selftest.py

# OS evaluation: CPU scheduling, race conditions, WFG, and Banker's algorithm (25 checks)
python os_layer.py
```

### 3. Machine Learning Model Training
Collects real lock telemetry under contention and fits the Random Forest classifier:
```bash
python collect_train.py
```

### 4. Empirical Benchmarks (Optional)
Executes all 6 configurations across multi-client workloads:
```bash
# Quick benchmark (2 seeds):
python benchmark.py --quick

# Full benchmark suite (5 seeds + worker concurrency sweep):
python benchmark.py
```

### 5. Launch the SafeLedger Dashboard
```bash
streamlit run dashboard.py
```

---

## PostgreSQL Mode (Optional)

SafeLedger defaults to an embedded SQLite database running in WAL mode with CRC32-checksummed write-ahead logs. To connect SafeLedger to an enterprise PostgreSQL server:

```powershell
# Windows PowerShell
$env:SAFELEDGER_PG_DSN="postgresql://safeledger:pass@localhost:5432/safeledger"
python seed_postgres.py
python selftest.py
streamlit run dashboard.py
```

```bash
# Linux / macOS
export SAFELEDGER_PG_DSN="postgresql://safeledger:pass@localhost:5432/safeledger"
python seed_postgres.py
python selftest.py
streamlit run dashboard.py
```
Unset `SAFELEDGER_PG_DSN` at any time to seamlessly return to the SQLite mode.

---

## Dashboard Architecture

The dashboard is structured into 10 modular pages:
1. **Overview**: Executive telemetry, system health, and benchmark aggregations.
2. **Concurrent Transaction Simulator**: Live multi-threaded workload simulator comparing 6 concurrency strategies.
3. **Deadlock Detection Lab**: Real opposite-transfer execution demonstrating Coffman conditions and DFS cycle detection.
4. **Banker's Algorithm**: Interactive safe-state and allocation matrix verification on textbook and banking environments.
5. **Machine Learning Risk Analysis**: Random Forest risk gate evaluation on runtime lock telemetry with fallback logic.
6. **Benchmark & Performance**: Throughput, P95 tail latency, retries, worker concurrency sweeps, and cloud cost projections.
7. **Operating System Concepts**: CPU scheduling (FCFS, RR, Priority+Aging), race condition demos, mutexes, and semaphores.
8. **DBMS Security & Recovery**: Write-Ahead Logging (WAL), ARIES crash recovery (redo/undo), PBKDF2 authentication, and tamper-evident audit hash chains.
9. **Banking Transaction Demo**: Real account transfer interface with RBAC ownership checks, limits, and idempotency.
10. **System & Database Status**: Python environment, database connection diagnostics, and asset integrity verification.
