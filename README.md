# SafeLedger
### A Concurrency-Safe Banking Transaction Engine with OS-Level Deadlock Handling and Predictive ML Risk Scoring

SafeLedger is an academic banking-engine simulation that explores how to process concurrent deposits, withdrawals, and transfers while preserving transaction correctness and managing deadlock risk. It combines operating-systems concepts, database transaction controls, and a machine-learning prediction service.

> **Project status:** This repository describes a prototype. The Random Forest model and Flask prediction service are documented as implemented; integration of ML risk scores into the live scheduler, full Write-Ahead Logging (WAL) recovery, the monitoring dashboard, and final comparative benchmarks are documented as in progress or pending. The eBPF collector is a working prototype with integration still pending.

## Why SafeLedger?

Concurrent transactions can cause problems such as:

- **Lost updates:** overlapping operations overwrite one another's changes.
- **Deadlocks:** transactions wait on resources held by one another, preventing progress.
- **Recovery challenges:** a failure during a transfer must not leave account balances partially updated.

SafeLedger demonstrates layered approaches to these problems. Rule-based synchronization and deadlock handling remain responsible for safety; the ML model provides an additional risk estimate rather than being the sole authority for transaction decisions.

## Architecture

The project is organized into five logical components:

| Component | Responsibility | Technologies / concepts |
|---|---|---|
| User interface | Submit transfers, inspect balances/history, and visualize system activity | Streamlit, Python |
| OS-level concurrency layer | Schedule transaction requests, synchronize access, avoid/detect deadlocks, select a victim | Java threads, mutexes, semaphores, scheduling algorithms, Banker's Algorithm, Wait-For Graph |
| Transaction and database layer | Persist account and transaction data and control transaction execution | Java, JDBC, PostgreSQL, ACID, row-level locks, Two-Phase Locking |
| Predictive ML service | Estimate deadlock risk from lock-contention features | Python, scikit-learn Random Forest, Flask REST API |
| Kernel telemetry collector | Observe Linux lock-wait events and derive features for the ML service | eBPF, BCC, futex tracing (Linux) |

### High-level transaction flow

1. A client submits a transfer request, including source account, destination account, amount, and priority.
2. The concurrency layer queues the request and assembles lock-contention features.
3. The ML service returns a deadlock-risk score when available.
4. The rule-based safety layer checks whether the request is safe. The documented policy is to deny unsafe requests, delay safe but high-risk requests, and grant safe low-risk requests.
5. For a granted transfer, account locks are acquired in ascending account-ID order and the database transaction performs the debit, credit, and transaction-record update.
6. The Wait-For Graph checks for cycles; if a deadlock is detected, the documented design selects a low-priority transaction as the victim.
7. The interface displays the transaction result and available monitoring information.

The ML service is not required for the rule-based safety path: the design specifies that the engine can fall back to Banker's Algorithm, ordered locks, and Wait-For Graph handling if the service is unavailable.

## Key Features and Concepts

### Concurrency and deadlock management

- **Scheduling:** FCFS, Round Robin, and Priority scheduling with aging are described in the project guide.
- **Synchronization:** mutexes and bounded semaphores coordinate concurrent operations.
- **Ordered locking:** acquire account locks in ascending account-ID order to reduce circular-wait risk.
- **Banker's Algorithm:** check whether granting a resource request leaves the system in a safe state.
- **Wait-For Graph:** represent transaction dependencies and use cycle detection to identify deadlocks.
- **Victim selection:** select a transaction for abort/retry to release resources when a cycle is detected.

### Database integrity

- PostgreSQL `Accounts` and `Transactions` tables.
- A balance check constraint and transaction lifecycle/status tracking.
- Java database access through JDBC.
- Row-level locking for concurrent account operations.
- ACID transaction concepts and Two-Phase Locking (2PL).

**Implementation note:** The project documents list WAL and crash-recovery integration in the Java transaction layer as pending/in progress. Do not assume full application-level recovery is complete solely because PostgreSQL itself provides WAL.

### Machine-learning risk prediction

The ML component uses a scikit-learn Random Forest classifier exposed through a Flask endpoint (`POST /predict`). The documented feature vector contains:

- `locks_held_on_target`
- `wait_queue_length`
- `account_contention_count`
- `wait_time_ms`
- `priority`

The service returns a risk score and a high-risk flag. The documented training data is synthetic lock-contention data, so its evaluation results should be interpreted in that context.

The project guide reports the following held-out evaluation results:

| Metric | Reported result |
|---|---:|
| Accuracy | 91.3% |
| Precision | 89.4% |
| Recall | 88.3% |

These are project-reported results on synthetic data, not evidence of equivalent performance on real banking workloads.

### eBPF lock telemetry (prototype)

The documented collector uses Linux eBPF/BCC futex tracing to observe lock-wait events and aggregate timing/contention information. It is intended to provide kernel-derived features to the same ML API. The documentation describes the collector as a prototype whose integration remains pending; Linux support and the necessary privileges/kernel headers are required.

## Technology Stack

- **Backend:** Java, JDBC
- **Database:** PostgreSQL
- **ML service:** Python, scikit-learn, Flask
- **Dashboard:** Streamlit
- **Kernel telemetry prototype:** eBPF, BCC (Linux)
- **Core topics:** concurrency control, scheduling, synchronization, deadlock prevention/avoidance/detection, ACID transactions, 2PL, WAL and recovery concepts

## Testing and Validation

The project documentation reports these checks:

- Account deposit/withdrawal balance constraint test: **Pass**
- Concurrent-transfer test for lost-update prevention using row locking: **Pass**
- Deadlock reproduction and detection test: **Pass**
- Random Forest evaluation on held-out synthetic data: **91.3% accuracy, 89.4% precision, 88.3% recall**

Final benchmarking of deadlock frequency and throughput with versus without the prediction layer is documented as pending. Results should be updated when that benchmark is completed.

## Project Structure

The documentation describes the components and interfaces, but does not provide a verified repository tree here. Use the actual repository layout when adding a file-by-file structure, setup commands, or run instructions.

## Setup and Running

Installation commands, environment variables, database initialization steps, and exact run commands are not specified in the project documents used to write this README. Please consult the repository's current source files and configuration before running the application. Avoid adding credentials or secrets to version control.

At a minimum, a local setup is expected to require the relevant Java runtime/build tooling, Python environment and dependencies, PostgreSQL, and (for the telemetry prototype) a compatible Linux environment with BCC/eBPF prerequisites.

## Team

**Team:** Zero DownTime  
**Project:** OSDBMS-V-2026-T176  
**Institution:** Graphic Era Deemed University

The project documentation lists Devansh Verma's assigned contribution as designing the PostgreSQL `Accounts` and `Transactions` tables, including the balance constraint and transaction status field. The team document lists other components as contributions from teammates.

## Limitations and Current Work

According to the project status documents:

- Integration of the ML risk score into the live scheduler is in progress.
- Java-layer WAL and crash-recovery integration is in progress.
- eBPF collector integration is pending; a prototype is documented as working.
- The Streamlit monitoring dashboard and live-data connection are in progress.
- Final comparative benchmarks are pending.
- The classifier is trained on synthetic data; real kernel telemetry is intended to extend the feature source.

## Repository

Source repository listed in the project documents:  
https://github.com/DevanshVerma-IND/SafeLedger

## Disclaimer

SafeLedger is an educational prototype for demonstrating OS, DBMS, concurrency, and ML concepts. It is **not production banking software** and has not been represented as independently audited, security-certified, or suitable for handling real customer funds.
